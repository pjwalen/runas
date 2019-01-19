#!/usr/bin/env python3

import argparse
import boto3
import datetime
import os
import pickle
import subprocess
import yaml

DURATION = 900
config_dir = os.path.join(os.environ['HOME'], '.runas')
cache_file = os.path.join(config_dir, 'cache')
config_file = os.path.join(config_dir, 'config')


class CacheFileCorrupt(Exception):
    pass


def assume_role(session_token, account):
    client = boto3.client(
        'sts',
        aws_access_key_id=session_token['AccessKeyId'],
        aws_secret_access_key=session_token['SecretAccessKey'],
        aws_session_token=session_token['SessionToken'],
        region_name=account['region']
    )
    response = client.assume_role(
        RoleArn='arn:aws:iam::{}:role/{}'.format(account['account-id'], account['role-arn']),
        RoleSessionName='PCS-Pipeline',
    )
    config_session_environment(response['Credentials'], account)


def config_session_environment(credentials, account):
    os.environ['AWS_ACCESS_KEY_ID'] = credentials['AccessKeyId']
    os.environ['AWS_SECRET_ACCESS_KEY'] = credentials['SecretAccessKey']
    os.environ['AWS_SESSION_TOKEN'] = credentials['SessionToken']
    os.environ['AWS_DEFAULT_REGION'] = account['region']
    

def get_args():
    # Parse the arguments
    parser = argparse.ArgumentParser(description='Deploy an applications cloudformation template.')
    parser.add_argument('--account', help='The account you want to run under.', required=True)
    parser.add_argument('command', nargs='*', help='The command to run')
    return parser.parse_args()


def get_cache_data():
    # Open the cache file and see if there is an existing session we can use.
    try:
        with open(cache_file, 'rb') as cachefp:
            cache_data = pickle.load(cachefp)
            if not isinstance(cache_data, dict):
                raise CacheFileCorrupt('The top level object of {} needs to be a dictionary.')
    except FileNotFoundError:
        # We need to seed the cache file with an empty dictionary.
        try:
            os.mkdir(config_dir)
        except FileExistsError:
            pass
        with open(cache_file, 'wb') as cachefp:
            pickle.dump({}, cachefp)
        cache_data = {}
    return cache_data


def get_config():
    with open(config_file) as configfp:
        config = yaml.load(configfp)
    return config


def get_session_token(profile, account):
    # Get cache data
    cache_data = get_cache_data()

    # Check if we have an existing session, if so use it
    try:
        cached_session = cache_data[account['profile']]
        if cached_session['Expiration'].replace(tzinfo=None) > datetime.datetime.now():
            return cached_session
    except KeyError:
        pass

    # If not, Create one
    token_code = input('MFA Code for {}: '.format(profile['mfa_serial']))
    client = boto3.client(
        'sts',
        aws_access_key_id=profile['aws_access_key_id'],
        aws_secret_access_key=profile['aws_secret_access_key'],
        region_name=account['region']
    )
    response = client.get_session_token(
        DurationSeconds=DURATION,
        SerialNumber=profile['mfa_serial'],
        TokenCode=token_code
    )

    # Write the created session to cache
    cache_data = get_cache_data()
    cache_data[account['profile']] = response['Credentials']
    write_cache_data(cache_data)
    return response['Credentials']


def write_cache_data(cache_data):
    with open(cache_file, 'wb') as cachefp:
        pickle.dump(cache_data, cachefp)


if __name__ == '__main__':
    args = get_args()
    config = get_config()
    account = config['accounts'][args.account]
    profile = config['profiles'][account['profile']]
    session_token = get_session_token(profile, account)
    assume_role(session_token, account)
    subprocess.call(args.command)
