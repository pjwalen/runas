#!/usr/bin/env python3

import argparse
import boto3
import dateutil.parser
import datetime
import os
import pytz
import sqlite3
import sys
import yaml

DURATION = 900
SERIAL_NUMBER = 'arn:aws:iam::056952386373:mfa/patrick.walentiny@pearson.com'
config_dir = os.path.join(os.environ['HOME'], '.runas')
cache_file = os.path.join(config_dir, 'cache')


class CacheFileCorrupt(Exception):
    pass


def assume_role(role):
    session_token = get_session_token()
    print(session_token)
    client = boto3.client('sts')
    account_id =client.get_caller_identity().get('Account')
    response = client.assume_role(
        RoleArn='arn:aws:iam::{}:role/{}'.format(account_id, role),
        RoleSessionName='PCS-Pipeline',
        aws_access_key_id=session_token['AccessKeyId'],
        aws_secret_access_key=session_token['SecretAccessKey'],
        aws_session_token=session_token['SessionToken']
    )
    config_session_environment(response['Credentials'])


def config_session_environment(credentials):
    os.environ['AWS_ACCESS_KEY_ID'] = credentials['AccessKeyId']
    os.environ['AWS_SECRET_KEY'] = credentials['SecretAccessKey']
    os.environ['AWS_SESSION_TOKEN'] = credentials['SessionToken']
    

def fix_dates(cache_data):
    for session in cache_data:
        cache_data[session]['Expiration'] = dateutil.parser.parse(cache_data[session]['Expiration']).replace(tzinfo=pytz.UTC)


def get_args():
    # Parse the arguments
    parser = argparse.ArgumentParser(description='Deploy an applications cloudformation template.')
    parser.add_argument('--profile', help='Set the AWS profile in ~/.aws/configure to use', required=True)
    return parser.parse_args()


def get_cache_data():
    # Open the cache file and see if there is an existing session we can use.
    try:
        with open(cache_file, 'r') as cachefp:
            cache_data = yaml.load(cachefp)
            fix_dates(cache_data)
            if not isinstance(cache_data, dict):
                raise CacheFileCorrupt('The top level object of {} needs to be a dictionary.')
    except FileNotFoundError:
        # We need to seed the cache file with an empty dictionary.
        os.mkdir(config_dir)
        with open(cache_file, 'w') as cachefp:
            yaml.dump({}, cachefp, default_flow_style=False)
        cache_data = {}
    return cache_data


def get_session_token():
    # Get cache data
    cache_data = get_cache_data()

    # Check if we have an existing session, if so use it
    try:
        cached_session = cache_data[os.environ['AWS_PROFILE']]
        print(cached_session['Expiration'])
        if cached_session['Expiration'] > datetime.datetime.now():
            return cached_session

    except KeyError:
        # If not, Create one
        token_code = input('MFA Code for {}: '.format(SERIAL_NUMBER))
        client = boto3.client('sts')
        response = client.get_session_token(
            DurationSeconds=DURATION,
            SerialNumber=SERIAL_NUMBER,
            TokenCode=token_code
        )

        # Write the created session to cache
        cache_data = get_cache_data()
        cache_data[os.environ['AWS_PROFILE']] = response['Credentials']
        write_cache_data(cache_data)
        return response['Credentials']


def write_cache_data(cache_data):
    cache_copy = dict(cache_data)
    for session in cache_copy:
        cache_copy[session]['Expiration'] = cache_copy[session]['Expiration'].replace(tzinfo=pytz.UTC).isoformat()
    with open(cache_file, 'w') as cachefp:
        yaml.dump(cache_copy, cachefp)
        


if __name__ == '__main__':
    args = get_args()
    os.environ['AWS_PROFILE'] = args.profile
    get_session_token()
    assume_role('PowerUser')
