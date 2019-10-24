from cachetools import LRUCache
from os.path import exists


class FileBackedCache(LRUCache):

    def popitem(self):
        key, value = super().popitem()
        print('Key "%s" evicted with value "%s"' % (key, value))
        if exists(value):
            print('Removing [{0}] file'.format(value))
        return key, value
