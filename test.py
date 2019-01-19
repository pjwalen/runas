#!/usr/bin/env python3

import datetime
import pickle

d = {
    'prod': {
        'Expiration': datetime.datetime.utcnow()
    }
}

with open('cache', 'wb') as fp:
    pickle.dump(d, fp)

with open('cache', 'rb') as fp:
    print(pickle.load(fp))
