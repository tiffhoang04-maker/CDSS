import pandas as pd
import uuid
import re
from random import randint
import streamlit as st
from io import BytesIO

#from .file import entry_table_file
from .path import (
	load_table,
	load_json,
	get_file_path,
	get_dir_path,
	get_neighbor_path,
	pages_str,
	data_str,
	functions_str,
)
#from .lst import type_lst

rename_col_dict = {
	"id_col": "ID",
	"pdb_id_col": "PDB ID",
	"pdb_code_col": "PDB Code",
}

def reorder_st_cols(df, row, col):

	class_lst = list(class_order_dict.keys())

	if row in class_lst:
		row_order = [x for x in class_order_dict[row] + ["All"] if x in list(df.index.values)] 

	if col in class_lst:
		col_order = [x for x in class_order_dict[col] + ["All"] if x in list(df.columns)] 

	if row in class_lst and col in class_lst:
		df = df.loc[row_order, col_order]
	elif row not in class_lst and col in class_lst:
		df = df.loc[:, col_order]
	elif row in class_lst and col not in class_lst:
		df = df.loc[row_order, :]
	
	return df

def get_st_file_path(st_file):

	return get_file_path(
		f"{randint(0,3261994)}_{st_file.name}",
		dir_path=get_neighbor_path(__file__, functions_str, data_str),
	)


def save_st_file(st_file):

	st_file_path = get_st_file_path(st_file)
	with open(st_file_path, "wb") as file:
		file.write(st_file.getbuffer())
	return st_file_path

def show_st_fig(fig, st_col=None):

	byt = BytesIO()
	fig.savefig(byt, format="png")
	if st_col is None:
		st.image(byt)
	else:
		st_col.image(byt)


def get_html_text(text_color_dict, font_size="medium", font_weight="normal"):

	html_str = ""
	for text, color in text_color_dict.items():

		size = font_size
		if type(font_size) == dict:
			size = font_size[text]

		weight = font_weight
		if type(font_weight) == dict:
			weight = font_weight[text]

		html_str += f'<span style="font-family:sans-serif; font-size: {size}; font-weight: {weight}; color:{color};">{text}</span>'

	return html_str


def load_st_table(file_path, file_name=None, json_format=False):

	if file_name is None:
		file_name = 'default_table.tsv'

	file_path = get_file_path(
			file_name,
			dir_path=get_dir_path(
				dir_path=get_neighbor_path(file_path, pages_str, data_str)
			))

	if json_format:
		return load_json(file_path)
	else:
		return load_table(file_path)
   



def rename_st_cols(df, col_lst=None):

	if col_lst is None:
		col_lst = [x for x in list(rename_col_dict.keys()) if x in list(df.columns)]

	return df.loc[:, col_lst].rename(columns=rename_col_dict)


def show_st_dataframe(df, st_col=None, hide_index=True):

	if hide_index:
		hide_dataframe_row_index = """
				<style>
				.row_heading.level0 {display:none}
				.blank {display:none}
				</style>
				"""

		st.markdown(hide_dataframe_row_index, unsafe_allow_html=True)

	if st_col is None:
		st.dataframe(df)
	else:
		st_col.dataframe(df)


def show_st_table(df, st_col=None, hide_index=True):

	if hide_index:
		hide_table_row_index = """
				<style>
				tbody th {display:none}
				.blank {display:none}
				</style>
				"""
		st.markdown(hide_table_row_index, unsafe_allow_html=True)

	if st_col is None:
		st.table(df)
	else:
		st_col.table(df)


def create_st_button(link_text, link_url, hover_color="#e78ac3", st_col=None):

	button_uuid = str(uuid.uuid4()).replace("-", "")
	button_id = re.sub("\d+", "", button_uuid)

	button_css = f"""
		<style>
			#{button_id} {{
				background-color: rgb(255, 255, 255);
				color: rgb(38, 39, 48);
				padding: 0.25em 0.38em;
				position: relative;
				text-decoration: none;
				border-radius: 4px;
				border-width: 1px;
				border-style: solid;
				border-color: rgb(230, 234, 241);
				border-image: initial;

			}}
			#{button_id}:hover {{
				border-color: {hover_color};
				color: {hover_color};
			}}
			#{button_id}:active {{
				box-shadow: none;
				background-color: {hover_color};
				color: white;
				}}
		</style> """

	html_str = f'<a href="{link_url}" target="_blank" id="{button_id}";>{link_text}</a><br></br>'

	if st_col is None:
		st.markdown(button_css + html_str, unsafe_allow_html=True)
	else:
		st_col.markdown(button_css + html_str, unsafe_allow_html=True)


def download_st_file(file_path, file_name, download_text, st_col=None):

	with open(file_path, "rb") as file:
		if st_col is None:
			st.download_button(download_text, file, file_name=file_name)
		else:
			st_col.download_button(download_text, file, file_name=file_name)


def encode_st_df(df):

	return df.to_csv(sep="\t", index=False).encode("utf-8")


def download_st_df(df, file_name, download_text, st_col=None):

	if st_col is None:
		st.download_button(
			label=download_text,
			data=encode_st_df(df),
			file_name=file_name,
		)
	else:
		st_col.download_button(
			label=download_text,
			data=encode_st_df(df),
			file_name=file_name,
		)

