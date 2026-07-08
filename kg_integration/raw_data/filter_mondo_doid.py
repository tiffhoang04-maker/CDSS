import pandas as pd

# Read the MONDO SSSOM mapping file
df = pd.read_csv(
    "mondo.sssom.tsv",
    sep="\t",
    comment="#",
    dtype=str
)

print("Columns:")
print(df.columns.tolist())

# Keep rows where MONDO maps to DOID
mondo_to_doid = df[
    df["subject_id"].str.startswith("MONDO:", na=False)
    & df["object_id"].str.startswith("DOID:", na=False)
].copy()

# Keep useful columns if they exist
wanted_columns = [
    "subject_id",
    "predicate_id",
    "object_id",
    "mapping_justification",
    "subject_label",
    "object_label",
    "mapping_provider"
]

existing_columns = [col for col in wanted_columns if col in mondo_to_doid.columns]

mondo_to_doid = mondo_to_doid[existing_columns]

# Rename columns to make them easier to understand
mondo_to_doid = mondo_to_doid.rename(columns={
    "subject_id": "mondo_id",
    "predicate_id": "mapping_type",
    "object_id": "doid_id",
    "subject_label": "mondo_label",
    "object_label": "doid_label"
})

# Save filtered mappings
mondo_to_doid.to_csv("mondo_doid_mappings.csv", index=False)

print("\nFirst few MONDO → DOID mappings:")
print(mondo_to_doid.head())

print("\nTotal MONDO → DOID mappings:", len(mondo_to_doid))

print("\nMapping types:")
print(mondo_to_doid["mapping_type"].value_counts())