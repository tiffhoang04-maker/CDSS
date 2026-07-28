from cdss_mcp_server.project_build.neo4j_logistics.neo4j_client import Neo4jClient
# run python test_neo4j_connection.py to test the connection to the Neo4j database
# you should see "Neo4j connection successful." if the connection is successful
# and connection_test: 1
# also all database info!
def main () -> None:
    client = Neo4jClient()

    server_info = client.driver.get_server_info(
        database=client.database
    )

    print(f"Configured URI: {client.uri}")
    print(f"Database: {client.database}")
    print(f"Username: {client.username}")
    print(f"Connected address: {server_info.address}")
    print(f"Neo4j server: {server_info.agent}")
    print(f"Bolt protocol: {server_info.protocol_version}")
    
    try:
        result = client.run_query("RETURN 1 AS connection_test")
        print("Neo4j connection successful.")
        print(result)

    finally:
        client.close()

if __name__ == "__main__":
    main()