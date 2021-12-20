"""
This script is responsible to get asset Details from the Qualys API for NCA account
"""
def lambda_handler(event,context):
    """
    step 1: Get the JWT Token
    step 2: call the asset API and get all the asset details
    step 3: push data into BigQuery
    """

    print("This is a lambda handler function from github actions 2")
