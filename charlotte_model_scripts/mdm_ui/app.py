import falcon
from falcon_multipart.middleware import MultipartMiddleware
from multiprocessing import Manager
from wsgiref.simple_server import make_server
import json
import os
import logging
import pandas as pd
import numpy as np
from get_mdm_next_stage import GetNextStageHandler
from get_mdm_next_stage_interactive import GetInteractiveNextStageHandler

# need to pull ollama model before running python app.py in terminal

#model_name = 'medllama2'
#model_name = 'wizardlm2'
model_name = 'mistral'
#model_name = 'gemma2'



log_filename="mdm_logs/mdm_api.log"
 
def open_gds(session_name='ALT', db='exmc'):
	from graphdatascience import GraphDataScience
	auth=('neo4j', os.getenv(session_name+'_NEO4J_P_1'))
	return GraphDataScience(os.getenv(session_name+'_NEO4J_URI_1'), auth=auth, database=db)

def get_manager():
	exmc_kg = open_gds(session_name='ALT', db='exmc')
	action_list_dict = {}
	action_list_dict['Initial Assessment Stage'] = list(exmc_kg.run_cypher("MATCH (n:Action {early_action:true}) RETURN DISTINCT n.phrase as n").n.unique())
	action_list_dict['Differential Diagnosis Stage'] = list(exmc_kg.run_cypher("MATCH (n:Action {is_action:true}) WHERE NOT n.phrase IS NULL RETURN DISTINCT n.phrase as n").n.unique())
	action_list_dict['Monitoring Stage'] = list(exmc_kg.run_cypher("MATCH (n:Action {general_monitor:true}) RETURN DISTINCT n.name as n").n.unique())
	#
	query = "MATCH (:Condition)-[:TREATS_MKtC]-(m:MedKit) RETURN %s"
	#props = ['name', 'route_of_use', 'strength_volume', 'location', 'qty_in_pack', 'side_effects']
	props = ['name', 'route_of_use', 'strength_volume', 'location']
	action_list_dict['Intervention Stage'] = exmc_kg.run_cypher(query % ','.join(['m.%s as %s' % (prop, prop) for prop in props]))
	exmc_kg.close()
	return [action_list_dict, model_name]

def create_app():
	manager = get_manager()
	logging.basicConfig(filename=log_filename,level=logging.INFO)
	#
	print('in app')
	api = falcon.App(middleware=[MultipartMiddleware()],cors_enable=True)
	api.add_route('/get_next_stage/{input_type}/{ehr_token}/{new_stage}', GetNextStageHandler(manager))
	#api.add_route('/get_next_stage_interactive/{input_type}/{ehr_token}/{new_stage}/{user_inputs}', GetInteractiveNextStageHandler(manager))
	api.add_route('/get_next_stage_interactive/', GetInteractiveNextStageHandler(manager))
	return api


def get_app():
	return create_app()


app=get_app()
