import os
import shutil
import gzip
import json
import pandas as pd
import numpy as np


rascore_str = "rascore"
build_str = "build"
classify_str = "classify"
cluster_str = "cluster"
plot_str = "plot"

util_str = "util"
pipelines_str = "pipelines"
data_str = "data"
pages_str = "pages"
functions_str = "functions"

order_col_lst = ['Stages', 'Actions', 'Diagnoses', 'Interventions']


def get_col_order(df):

	df_col_lst = list(df.columns)

	col_lst = list()
	for order_col in order_col_lst:
		if order_col in df_col_lst:
			col_lst.append(order_col)
		if order_col in data_col_lst:
			for col in get_val_col_lst(df, order_col):
				if col not in col_lst:
					col_lst.append(col)

	for col in df_col_lst:
		if col not in col_lst:
			col_lst.append(col)

	return col_lst

def order_cols(df, col_lst):

	df = df.reindex(columns=col_lst)

	return df

def order_rows(df, col_lst=None, reset_index=False):

	df_col_lst = list(df.columns)

	if col_lst is None:
		col_lst = list()

	if len(col_lst) > 0:
		df = df.sort_values(by=col_lst)

	if reset_index:
		df = df.reset_index(drop=True)

	return df


def path_exists(path):

	exists = False
	if path is not None:
		if os.path.isfile(path):
			exists = True
		elif os.path.isdir(path):
			exists = True

	return exists


def append_path(path):

	if not path_exists(path):
		os.makedirs(path)


def get_dir_name(dir_path):

	if "/" in dir_path:
		dir_name = dir_path.rsplit("/", 1)[0]
	else:
		dir_name = os.getcwd()

	return dir_name


def get_file_name(path):

	if "/" in path:
		file_name = path.rsplit("/", 1)[1]
	else:
		file_name = path

	return file_name


def append_file_path(path):

	append_path(get_dir_name(path))


def delete_path(path):

	if path_exists(path):
		if os.path.isfile(path):
			os.remove(path)
		elif os.path.isdir(path):
			shutil.rmtree(path)


def copy_path(source_path, dest_path):

	if path_exists(dest_path):
		delete_path(dest_path)
	shutil.copyfile(source_path, dest_path)


def save_table(path, df, sep="\t", header=True, index=False, fillna="None"):

	append_file_path(path)

	df = df.fillna(fillna)
	df = order_cols(df, get_col_order(df))
	df = order_rows(df)

	df.to_csv(path, sep=sep, header=header, index=index)


def load_table(path, sep="\t", fillna="None"):

	if path_exists(path):
		df = pd.read_csv(path, sep=sep, dtype=str)

		df = df.fillna(fillna)
		df = order_cols(df, get_col_order(df))
		df = order_rows(df)
	else:
		df = None

	return df


def save_matrix(path, matrix, delim=","):

	append_file_path(path)

	np.savetxt(path, matrix, delimiter=delim)


def load_matrix(path, delim=","):

	if path_exists(path):
		matrix = np.loadtxt(path, delimiter=delim)
	else:
		matrix = None

	return matrix


def save_lst(path, val_lst):

	append_file_path(path)

	with open(path, "w") as file:
		for val in val_lst:
			file.write(f"{val}\n")


def load_lst(path):

	if path_exists(path):
		with open(path, "r") as file:
			line_lst = file.read().splitlines()
	else:
		line_lst = None

	return line_lst


def save_json(path, json_dict):

	append_file_path(path)

	with open(path, "w") as file:
		json.dump(json_dict, file)


def load_json(path):

	if path_exists(path):
		with open(path, "r") as file:
			json_dict = json.load(file)
	else:
		json_dict = None

	return json_dict


def unzip_file(in_path, out_path=None):

	if out_path is None:
		out_path = in_path.replace(".gz", "")

	with gzip.open(in_path, "rb") as file_in:
		with open(out_path, "wb") as file_out:
			shutil.copyfileobj(file_in, file_out)


def search_dir(dir_path, file_str):

	return [x for x in os.listdir(dir_path) if file_str in x]


def get_dir_path(dir_str=None, dir_path=None):

	if dir_path is None:
		dir_path = os.getcwd()

	if dir_str is not None:
		dir_path += f"/{dir_str}"

	return dir_path


def get_file_path(file_name, dir_str=None, dir_path=None, pre_str=True):

	file_path = get_dir_path(dir_str=dir_str, dir_path=dir_path)
	file_path += "/"
	if pre_str and dir_str != None:
		file_path += dir_str
		file_path += "_"
	file_path += file_name

	return file_path


def get_neighbor_path(file_path, dir_str, neighbor_str):

	dir_path = get_dir_name(file_path)
	dir_path = dir_path.split(dir_str)[0]
	dir_path += neighbor_str

	return dir_path