import pandas as pd
import time
import numpy as np
import json
import re
from datetime import datetime, timedelta

class MedicalInformation():
	def __init__(self, cm_name):
		#
		self.cm_name = cm_name
		self.start_date = datetime(2024, 8, 5, 6)
		self.elapsed_time = 0
		# actions and stages
		self.cm_info_dict = {}
		self.seen_actions = []
		self.seen_stages = []
		# diagnoses
		self.potential_disease_str = ''
		self.early_diseases = []
		self.high_severity_diag = []
		self.low_severity_diag = []
		self.eliminated_diag = []
		# symptoms
		self.symptom_list = []
		# presciptions
		self.rx_list = []
		# interactive info
		self.interactive_result = []
	#
	def get_current_time(self):
		return (self.start_date+timedelta(minutes=self.elapsed_time)).strftime('Date: %B %d %Y Time: %H:%M')
	#
	def get_medical_infomation(self):
		crew_member_info_types, crew_member_info = list(self.cm_info_dict.keys()), list(self.cm_info_dict.values())
		med_info = ''.join(['%s:%s\n\n' % (info_type, info) for info_type, info in zip(crew_member_info_types, crew_member_info)])
		med_info = 'Medical Information:\n%s' % med_info
		if len(self.rx_list) > 0:
			med_info += 'Intervention Information:\n%s\n'%'\n'.join(self.rx_list)
		return med_info
	#
	def get_probable_diag_information(self):
		diag_info = ""
		if len(self.high_severity_diag+self.low_severity_diag+self.eliminated_diag)>0:
			diag_info = "Probable Diagnoses:"
			diag_info = self.add_to_diag_str(diag_info, 'High Severity Probable Diagnoses', self.high_severity_diag)
			diag_info = self.add_to_diag_str(diag_info, 'Low Severity Probable Diagnoses', self.low_severity_diag)
			diag_info = self.add_to_diag_str(diag_info, 'Eliminated Diagnoses', self.eliminated_diag)
		return diag_info
	#
	def add_to_diag_str(self, diag_info, subtitle, diag_list):
		if len(diag_list) > 0:
			diag_info += '\n%s:\n' % subtitle
			diag_info += '\n'.join(diag_list)+'\n'
		return diag_info
	#
	def get_medical_sections(self):
		crew_member_info_types = list(self.cm_info_dict.keys())
		read_info = crew_member_info_types[-1]
		if len(crew_member_info_types)>1:
			read_info = ', '.join(crew_member_info_types[:-1])+', and '+read_info
		return read_info



