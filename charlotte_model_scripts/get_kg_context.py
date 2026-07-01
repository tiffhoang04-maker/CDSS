import pandas as pd
import time
import numpy as np
import json
import re
from datetime import datetime, timedelta
from ast import literal_eval
from get_kg_actions import actions_vectorstore

# (6) turns graph relationships into readable clinical background for prompts
# maps symptoms to possible diseases 
# finds actions related to diseases
# converts action phrases to action names
# builds diagnosis or medication context for the LLM

abnormal_results = ['Abnormal','sinus tachycardia', 'Elevated','High Blood Pressure Stage 1','High Blood Pressure Stage 2','Hypertensive Crisis', 'Low', 'High']
abnormal_result_pattern = re.compile(r'%s' % '|'.join(abnormal_results))

def get_diseases_of_symptoms(kg, cm_medical_info):
	query = """WITH %s as symptom_list 
		MATCH (s:Symptom)-[]-(n:Disease) where s.name IN symptom_list
		WITH COLLECT(DISTINCT n.name) AS disease_names
		MATCH (n:Disease)<-[:ISA_DiD]-(n2:Disease)-[]-(:Condition) WHERE n.name IN disease_names
		WITH COLLECT(DISTINCT(n2.name)) AS extra_names, disease_names
		WITH  extra_names+disease_names AS diseases
		MATCH (:Condition)-[]-(n:Disease) WHERE n.name IN diseases
		RETURN DISTINCT n.name as d"""
	symptom_list = [actions_vectorstore['Symptom'].similarity_search_with_score(symptom, k=1)[0][0].page_content for symptom in cm_medical_info.symptom_list]
	cm_medical_info.early_diseases = list(kg.run_cypher(query % symptom_list).d.unique())
	potential_disease_str = "The crew member's symptoms are common in the following diseases: %s" % ', '.join(cm_medical_info.early_diseases)
	if len(cm_medical_info.early_diseases) == 0:
		potential_disease_str = ""
	return cm_medical_info, potential_disease_str

def get_actions_of_diseases(kg, disease_list, action_list):
	query = """WITH %s as disease_list, %s as action_list
	MATCH (n1:Action|MedKit {early_action:true})-[]-(:Condition)-[]-(n2:Disease) 
	WHERE n2.name IN disease_list AND n1.phrase in action_list RETURN DISTINCT n1.phrase as n"""
	filtered_actions = kg.run_cypher(query % (disease_list, action_list)).n.unique()
	filtered_actions = [a.strip('.') for a in filtered_actions]
	action_str = 'Early actions to test for these diseases include: %s' % ', '.join(filtered_actions)
	if len(filtered_actions)==0:
		action_str = ''
	return action_str

def get_action_phrase_to_name(action, kg):
	query = 'MATCH (n:Action|MedKit {phrase:"%s"}) RETURN DISTINCT n.name as n'
	action = kg.run_cypher(query % action).n.values[0]
	return action

def early_diagnosis_context(kg, cm_medical_info):
	seen_categories = list(set(cm_medical_info.cm_info_dict.keys())-set(['EHRS', 'PAIN SURVEY']))
	abnormal_value_list, abnormal_list = [], []
	for category in seen_categories:
		for row in cm_medical_info.cm_info_dict[category].strip().split('\n'):
			result = re.split(r'Time: [0-9]{2}:[0-9]{2} ', row)[-1]
			if len(abnormal_result_pattern.findall(result))>0:
				abnormal_list.append(result.split(':')[0])
				abnormal_value_list.append(result)
	#
	action_str = ', %s as action_list' % abnormal_list
	action_filter = 'a.name IN action_list' if len(abnormal_list)>0 else 'a.early_action = true'
	context = get_diagnosis_context(kg, cm_medical_info, action_str, action_filter)
	return context	



def get_diagnosis_context(kg, cm_medical_info, action_str, action_filter):
	query = """WITH %s as disease_list%s
	MATCH p=(n:Disease|Symptom)-[:PRESENTS_DpS|MAPSTO_CmS|ISA_DiD|MAPSTO_CmD*0..2]-(:Condition)-[]-(a:Action)
	WHERE n.name in disease_list AND %s
	UNWIND relationships(p) as rel
	WITH COLLECT(DISTINCT elementId(rel)) as rel_ids
	MATCH (n1)-[r]->(n2) WHERE elementId(r) IN rel_ids
	RETURN DISTINCT HEAD(LABELS(n1)) as nt1, n1.name as n1, HEAD(LABELS(n2)) as nt2, n2.name as n2, TYPE(r) as edge"""
	rel_df = kg.run_cypher(query % (cm_medical_info.early_diseases, action_str, action_filter))
	print(query % (cm_medical_info.early_diseases, action_str, action_filter))
	#
	edge_context_dict ={'PRESENTS_DpS': ['%s is a common symptom of the following diseases: %s.', 'n2'],
		'ISA_DiD': ['%s is similar to the following diseases: %s.', 'n1']}
	context = []
	for action in rel_df[rel_df.nt1.isin(['Action', 'MedKit'])].n1.unique():
		conditions = rel_df[(rel_df.n1==action)&(rel_df.nt2=='Condition')].n2.unique()
		mapped_phenos = rel_df[(rel_df.n1.isin(conditions))&(rel_df.nt2.isin(['Symptom', 'Disease']))].n2.unique()
		context.append("%s is commonly used when diagnosing the following conditions: %s." % (action, ', '.join(mapped_phenos)))
	for edge in rel_df[rel_df.edge.isin(list(edge_context_dict.keys()))].edge.unique():
		context_str, n = edge_context_dict[edge]
		n2 = 'n1' if n == 'n2' else 'n2'
		df = rel_df[(rel_df.edge==edge)]
		if edge == 'ISA_DiD':
			df = df[~df.n2.isin(cm_medical_info.early_diseases)]
		df = df[[n, n2]].groupby(n)[n2].apply(list).reset_index()
		for n1, n2_list in df.values:
			context.append(context_str % (n1,  ', '.join(n2_list)))
	context = '\n'.join(context)
	return context	




def get_rx_context(kg, cm_medical_info):
	query = """WITH %s as disease_list
	MATCH p=(n:Disease|Symptom)-[:PRESENTS_DpS|MAPSTO_CmS|ISA_DiD|MAPSTO_CmD*0..2]-(:Condition)-[:TREATS_MKtC]-(:MedKit)
	WHERE n.name in disease_list
	UNWIND relationships(p) as rel
	WITH COLLECT(DISTINCT elementId(rel)) as rel_ids
	MATCH (n1)-[r]->(n2) WHERE elementId(r) IN rel_ids
	RETURN DISTINCT HEAD(LABELS(n1)) as nt1, n1.name as n1, HEAD(LABELS(n2)) as nt2, n2.name as n2, TYPE(r) as edge, n1.is_category as is_category"""
	rel_df = kg.run_cypher(query % (cm_medical_info.early_diseases))
	treatments = list(rel_df[(rel_df.is_category!=True)&(rel_df.nt1=='MedKit')&(rel_df.edge=='TREATS_MKtC')].n1.unique())
	treatment_categories = list(rel_df[(rel_df.is_category==True)&(rel_df.nt1=='MedKit')].n1.unique())
	#
	query = """WITH %s as treatments
	MATCH (n1:MedKit)-[:INCLUDES_MKiMK]->(n2:MedKit) WHERE %s.name IN treatments
	RETURN DISTINCT n2.name as n1, n1.name as category"""
	category_df = rel_df[rel_df.edge=='TREATS_MKtC']
	category_df = pd.concat((category_df[category_df.is_category==True].rename(columns={'n1':'category'}).merge(kg.run_cypher(query % (treatment_categories, 'n1')), on='category'), 
		category_df[category_df.is_category==False].merge(kg.run_cypher(query % (treatments, 'n2')), on='n1') ),axis=0)
	category_df = category_df.drop(['nt2', 'is_category'], axis=1).rename(columns={'n2':'condition'})
	category_df = category_df.merge(rel_df[rel_df.edge.isin(['MAPSTO_CmS','MAPSTO_CmD'])].rename(columns={'n1':'condition'}).drop(['nt1', 'edge', 'is_category'],axis=1), on='condition')
	category_df = category_df[['n1', 'category', 'n2']].drop_duplicates().groupby(['n1', 'category'])['n2'].apply(list).reset_index()
	#
	context = []
	for category in category_df.category.unique():
		context.append('%s Treatments:' % category)
		for n1, conditions in category_df[category_df.category==category][['n1', 'n2']].values:
			context.append("%s is commonly used to treat or palliate the following conditions: %s." % (n1, ', '.join(conditions)))
	#
	edge_context_dict ={'PRESENTS_DpS': ['%s is a common symptom of the following diseases: %s.', 'n2'],
	'ISA_DiD': ['%s is similar to the following diseases: %s.', 'n1']}
	rel_df = rel_df[rel_df.edge.isin(list(edge_context_dict.keys()))]
	for edge in rel_df.edge.unique():
		context_str, n = edge_context_dict[edge]
		n2 = 'n1' if n == 'n2' else 'n2'
		df = rel_df[(rel_df.edge==edge)]
		if edge == 'ISA_DiD':
			df = df[~df.n2.isin(cm_medical_info.early_diseases)]
		df = df[[n, n2]].groupby(n)[n2].apply(list).reset_index()
		for n1, n2_list in df.values:
			context.append(context_str % (n1,  ', '.join(n2_list)))
	context = '\n'.join(context)
	return context
