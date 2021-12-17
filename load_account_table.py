#!/usr/bin/env python3
import os
import botocore
import boto3
import csv
import boto3
import psycopg2
from datetime import datetime

account_list = {}

connection = psycopg2.connect( user="postgres", host = "cseo.cluster-cedjfqr1nhow.us-east-1.rds.amazonaws.com",
                          port=5432,
                          database='audit',
                          sslmode="disable",
                          connect_timeout=10)

cursor = connection.cursor()

def describeOrg(client, root_account, ou):
   child_paginator = client.get_paginator('list_children')
   child_iterator = child_paginator.paginate(ParentId=ou, ChildType='ACCOUNT')
   for child_itr in child_iterator:
      for acc in child_itr['Children']:
          response = client.describe_account( AccountId=acc['Id'])['Account']

          parentId = root_account.strip()
          accountId = response['Id'].strip()
          arn = response['Arn'].strip()
          name = response['Name'].strip()
          status = response['Status'].strip()
          email = response['Email'].strip()
          method = response['JoinedMethod']
          joined = response['JoinedTimestamp']

          try:
             cursor.execute("set datestyle = ISO; INSERT INTO accounts(accountid, name, org_name, description, parent_accountid, arn, email, status, orgid, csp, joined_timestamp, joined_method) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);", (accountId, name, account_list[root_account]['Name'], "Description", root_account, arn, email, status, ou, "AWS", joined.isoformat(), method));
          except (Exception, psycopg2.Error) as e:
              connection.rollback()
              if ((e.pgcode == '25P02') or (e.pgcode=='23505')):
                 print ("Record already exists")
                 sql = "set datestyle=ISO;UPDATE accounts set name='{}', parent_accountid='{}', email='{}', status='{}', orgid='{}', created=now(), joined_timestamp = '{}', joined_method='{}'  where accountid='{}'".format(name, root_account, email, status, ou, joined.isoformat(), method, accountId)
                 print("Update: {}".format(sql))
                 cursor.execute(sql)
                 connection.commit()
              else:
                print ("OOO Error while connecting to PostgreSQL", e)
          else:
             connection.commit()
          print("OU: {} Account:  {} {} {} {} {}".format(ou, response['Id'], response['Arn'], response['Name'], response['Status'], response['Email']))


   child_paginator = client.get_paginator('list_children')
   child_iterator = child_paginator.paginate(ParentId=ou, ChildType='ORGANIZATIONAL_UNIT')
   for child_itr in child_iterator:
      for acc in child_itr['Children']:
          response = client.describe_organizational_unit(OrganizationalUnitId=acc['Id'])['OrganizationalUnit']
          rootId = response['Id'].strip()
          arn = response['Arn'].strip()
          name = response['Name'].strip()

          print(response)
          cursor.execute("INSERT INTO organizations(orgId, arn, name, parentOrgId) VALUES (%s, %s,  %s, %s);", (rootId, arn, name, ou));
          connection.commit()

          print("RootOU: {} OU:  {} {} - {}".format(ou, response['Id'], response['Arn'], response['Name']))

          describeOrg(client, root_account, response['Id'] )


def main():
    print("load_account_table.py")
    print("")

    sql = "delete from organizations;"
    cursor.execute(sql)
    connection.commit()

    with open('../../accounts/aws-master-payers.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            account_list[row[0]] = {'Name': row[1].strip()}


    """Call the script to run against the list of provided accounts."""
    sts_client = boto3.client('sts')

    for root_account in account_list:
        print("------------------------------------------------------------------------------")
        print("AccountID: {} ({}) ".format(root_account, account_list[root_account]['Name']))

        try:
            creds = sts_client.assume_role(
              RoleArn="arn:aws:iam::{}:role/{}".format(root_account, 'Global_CSEO_Auto_ReadOnly'),
              RoleSessionName='Global-Runner',
              DurationSeconds=3600
            )['Credentials']

            o_client = boto3.client('organizations', region_name="us-east-1",
                      aws_access_key_id=creds['AccessKeyId'],
                      aws_secret_access_key=creds['SecretAccessKey'],
                      aws_session_token=creds['SessionToken'])

            org = o_client.describe_organization()

            print("OrganizationId: {}".format(org['Organization']['Id']))

            root_paginator = o_client.get_paginator('list_roots')
            root_iterator = root_paginator.paginate()

            for root_itr in root_iterator:
             for acc in root_itr['Roots']:
                   rootId = acc['Id'].strip()
                   arn = acc['Arn'].strip()
                   name = acc['Name'].strip()

                   cursor.execute("INSERT INTO organizations(orgid, arn, name, parentorgid) VALUES (%s, %s,  %s, %s);", (rootId, arn, name, None));
                   connection.commit()

                   print("ROOT  {} {} {}".format(rootId, arn, name))

                   describeOrg(o_client, root_account, rootId)
        except (Exception, psycopg2.Error) as e:
            print("Error processing root account: {} {}".format(root_account, account_list[root_account]['Name']))
            print(e)
            pass

    print("Clearing removed accounts...")
    sql = "delete from accounts where csp='AWS' and accountid in (select accountid from accounts WHERE csp='AWS' AND (created < current_timestamp - interval '24 hours') )"
    cursor.execute(sql);
    connection.commit()

if __name__ == '__main__':
    main()
   
