from __future__ import print_function
import os.path
import pickle


def load_cache(cache_to_load, cache_file):
    if os.path.isfile(cache_file):
        with open(cache_file, 'rb') as f:
            jj = pickle.load(f)
            for row in jj:
                cache_to_load[row['key']] = row['entry']


def save_cache(cache_to_save, cache_file):
    with open(cache_file, 'wb') as f:
        data = []
        for key in cache_to_save:
            data.append({'key': key, 'entry': cache_to_save[key]})
        pickle.dump(data, f)


class CacheUtil:
    def __init__(self, cache, cache_file, debug=False):
        self.cache = cache
        self.cache_file = cache_file
        self.debug = debug

    def load(self):
        if self.debug is True:
            print("util cursize before load {0}".format(self.cache.currsize))
        loaded_cache = None

        if self.cache_file is not None and os.path.isfile(self.cache_file):
            if self.debug is True:
                print("loading cache")
            with open(self.cache_file, 'rb') as f:
                loaded_cache = pickle.load(f)

        if type(self.cache) == type(loaded_cache):
            self.cache = loaded_cache
            if self.debug is True:
                print("Got reasonable cache!")

        if self.debug is True:
            print("util cursize after load {0}".format(self.cache.currsize))

    def save(self):
        if self.cache is None:
            return

        if self.debug is True:
            print("Saving cache to file.")
        if self.cache_file is not None and len(self.cache_file) > 0:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)

    def get_cache(self):
        return self.cache
