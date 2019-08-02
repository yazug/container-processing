from cachetools import LRUCache
from cachetools import TTLCache
from koji_wrapper.base import KojiWrapperBase
from koji_wrapper.tag import KojiTag
import os
import os.path
import pickle

CACHE_PATH = "~/.cache/container-processing"


# TODO(jmls): reflect this is caching for container images
class CachingKojiWrapper(KojiWrapperBase):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._build_data = TTLCache(maxsize=6000, ttl=604800)
        self._task_results = TTLCache(maxsize=8000, ttl=604800)
        self._build_id_to_parent_id = LRUCache(maxsize=16000)
        self._build_id_to_build_task_id = LRUCache(maxsize=16000)
        self._nvr_to_build_id = LRUCache(maxsize=16000)
        self._build_id_to_nvr = LRUCache(maxsize=16000)

    def _load_one(self, path, filename, default=None, debug=False):
        cache_in = default
        filename = os.path.join(path, filename)
        if os.path.exists(filename):
            with open(filename, 'rb') as fin:
                cache_in = pickle.load(fin)
                if debug:
                    print("Loaded {0} entries from {1}".format(cache_in.currsize, filename))
        return cache_in

    def _cross_populate_cache(self):

        # populate direct lookup caches from build data entries have
        for build_id, val in self._build_data.items():
            if val is None:
                continue

            if val['nvr'] not in self._nvr_to_build_id:
                self._nvr_to_build_id[val['nvr']] = build_id

            if build_id not in self._build_id_to_nvr:
                self._build_id_to_nvr[build_id] = val['nvr']

            if 'extra' not in val or val['extra'] is None:
                continue

            if 'container_koji_task_id' in val['extra']:
                self._build_id_to_build_task_id[build_id] = int(val['extra']['container_koji_task_id'])

            if 'image' in val['extra'] and 'parent_build_id' in val['extra']['image']:
                parent_build_id = int(val['extra']['image']['parent_build_id'])
                if parent_build_id is not None:
                    self._build_id_to_parent_id[build_id] = parent_build_id

        # populate _build_id_to_build_task_id from task results
        for task_id, val in self._task_results.items():
            # if not valid task results for a container image skip it
            if 'repositories' not in val:
                continue

            if 'koji_builds' in val:
                for build_id in [int(build_id) for build_id in val['koji_builds']]:
                    if build_id not in self._build_id_to_build_task_id:
                        self._build_id_to_build_task_id[int(build_id)] = task_id

        # populate _build_id_to_nvr from _nvr_to_build_id
        for nvr in set(self._build_id_to_nvr.values()) - set(self._nvr_to_build_id):
            build_id = self._nvr_to_build_id[nvr]
            if build_id is not None:
                self._build_id_to_nvr[build_id] = nvr

        # populate _nvr_to_build_id from _build_to_nvr
        for build_id in set(self._nvr_to_build_id.values()) - set(self._build_id_to_nvr):
            nvr = self._build_id_to_nvr[build_id]
            if nvr is not None:
                self._nvr_to_build_id[nvr] = build_id

    def load_cache(self, path=CACHE_PATH, debug=False):
        cache_path = os.path.expanduser(path)

        self._build_id_to_parent_id = self._load_one(
            cache_path, 'build_id_to_parent_id', self._build_id_to_parent_id, debug=debug)
        self._nvr_to_build_id = self._load_one(
            cache_path, 'build_id_or_nvr_to_build_id', self._nvr_to_build_id,
            debug=debug)
        self._build_id_to_build_task_id = self._load_one(
            cache_path, 'build_id_to_build_task_id', self._build_id_to_build_task_id, debug=debug)

        self._build_data = self._load_one(cache_path, 'build_data', self._build_data, debug=debug)
        self._task_results = self._load_one(cache_path, 'task_results', self._task_results, debug=debug)
        self._build_id_to_nvr = self._load_one(
            cache_path, 'build_id_to_nvr', self._build_id_to_nvr, debug=debug)

        self._cross_populate_cache()

    def save_cache(self, path=CACHE_PATH, debug=False):
        cache_path = os.path.expanduser(path)

        if not os.path.isdir(cache_path):
            os.makedirs(cache_path)

        for filename, cache in [('build_id_to_parent_id', self._build_id_to_parent_id),
                                ('build_id_to_build_task_id', self._build_id_to_build_task_id),
                                ('build_data', self._build_data),
                                ('task_results', self._task_results),
                                ('nvr_to_build_id', self._nvr_to_build_id),
                                ('build_id_to_nvr', self._build_id_to_nvr)]:

            with open(os.path.join(cache_path, filename), 'wb') as fout:
                pickle.dump(cache, fout)
                if debug:
                    print("saving {0} now with {1}".format(filename, cache.currsize))

    # Search for batch for a tag (will not pick up isolated builds)
    def get_matching_batch_from_tag(self, osp, rhel, batch, latest=False, sub_tag='candidate'):
        """Get matching container images from koji_tag"""
        tag = "rhos-{0}-rhel-{1}-{2}".format(float(osp), rhel, sub_tag)
        koji_tag = KojiTag(session=self, tag=tag)

        koji_tag.builds(latest=latest, type='image', inherit=False)

        return self.get_matching_batch_from_koji_tag(koji_tag, batch)

    def get_build_trees(self, matching_containers):

        trees = []
        for value in matching_containers.values():
            for build in value.values():
                if 'parent_build_id' in build:
                    build_id = build['build_id']
                    parent_build_id = build['parent_build_id']
                    trees.append((parent_build_id, build_id))
        print(trees)

        return trees

    def get_matching_batch_from_koji_tag(self, koji_tag, batch):
        matching_containers = {}
        for build in koji_tag.builds():
            if '-container' not in build['package_name']:
                continue

            record = self.getRecordForBuild(build['id'], grab_build_task_info=True)
            component = record['package_name']

            if 'task_pullspecs' in record and [i for i in record['task_pullspecs'] if batch in i]:
                if component not in matching_containers:
                    matching_containers[component] = {}
                matching_containers[component][record['build_id']] = record
            else:
                continue

            if 'parent_build_id' in record:
                parent_record = self.getRecordForBuild(record['parent_build_id'])
                parent_component = parent_record['package_name']
                if 'openstack' in parent_component:
                    print("Adding {0} as parent of {1}".format(parent_record['nvr'], record['nvr']))
                    if parent_component not in matching_containers:
                        matching_containers[parent_component] = {}
                    matching_containers[parent_component][parent_record['build_id']] = parent_record
        return matching_containers

    def get_latest_cdn_containers(self, osp, rhel, latest=True, extra_info=False):
        tag = "rhos-{0}-rhel-{1}-container-released".format(float(osp), rhel)
        koji_tag = KojiTag(session=self, tag=tag)

        koji_tag.builds(latest=latest, type='image', inherit=False)

        return self.get_container_builds_from_koji_tag(koji_tag, get_extra_info=extra_info)

    def get_list_containers(self, osp, rhel, sub_tag='candidate', latest=False, inherit=False):
        """Load Cache with builds from a tag"""
        tag = "rhos-{0}-rhel-{1}-{2}".format(float(osp), rhel, sub_tag)
        koji_tag = KojiTag(session=self, tag=tag)

        koji_tag.builds(latest=latest, type='image', inherit=inherit)
        containers = set()
        for i in koji_tag.builds():
            if 'container' in i['package_name']:
                if i['nvr'] not in self._nvr_to_build_id:
                    self._nvr_to_build_id[i['nvr']] = i['build_id']
                self._build_id_to_nvr[i['build_id']] = i['nvr']
                containers.add(i['nvr'])
        return containers

    def getParentBuildId(self, build_id_or_nvr):
        build_id = self.getBuildId(build_id_or_nvr)
        if build_id not in self._build_id_to_parent_id:
            build_data = self.build(build_id)

            if build_id not in self._build_id_to_parent_id and 'extra' in build_data and build_data['extra'] is not None and 'image' in build_data['extra'] and 'parent_build_id' in build_data['extra']['image']:
                self._build_id_to_parent_id[build_id] = int(build_data['extra']['image']['parent_build_id'])
            else:
                self._build_id_to_parent_id[build_id] = None

        if build_id in self._build_id_to_parent_id:
            return self._build_id_to_parent_id[build_id]

        return None

    def get_package_name(self, build_id_or_nvr):
        build_data = self.build(build_id_or_nvr)
        if build_data:
            return build_data['package_name']

        return None

    def getBuildId(self, build_id_or_nvr):
        build_id = None

        try:
            build_id = int(build_id_or_nvr)
        except ValueError:
            pass

        if build_id is None and build_id_or_nvr in self._build_id_to_nvr:
            build_id = build_id_or_nvr

        if build_id is None and build_id_or_nvr in self._nvr_to_build_id:
            build_id = self._nvr_to_build_id[build_id_or_nvr]

        if build_id is None:
            build_data = self.build(build_id_or_nvr)
            build_id = build_data['id']

        return build_id

    def get_nvr(self, build_id_or_nvr):
        build_id = self.getBuildId(build_id_or_nvr)

        if build_id is None or build_id not in self._build_id_to_nvr:
            build_data = self.build(build_id_or_nvr)
            return build_data['nvr']

        return self._build_id_to_nvr[build_id]

    def build(self, build_id_or_nvr):

        build_id = None

        try:
            build_id_or_nvr = int(build_id_or_nvr)
        except ValueError:
            pass

        if build_id_or_nvr in self._build_data or build_id_or_nvr in self._build_id_to_nvr:
            build_id = int(build_id_or_nvr)

        if build_id is None and build_id_or_nvr in self._nvr_to_build_id:
            build_id = self._nvr_to_build_id[build_id_or_nvr]

        if (build_id is None or build_id not in self._build_data):
            builddata = super().build(build_id_or_nvr)

            build_id = builddata['id']

            self._build_data[build_id] = builddata
            self._nvr_to_build_id[builddata['nvr']] = builddata['id']
            if 'parent_build_id' in builddata['extra']['image']:
                self._build_id_to_parent_id[build_id] = builddata['extra']['image']['parent_build_id']
            else:
                self._build_id_to_parent_id[build_id] = None
            self._build_id_to_build_task_id[build_id] = builddata['extra']['container_koji_task_id']

        return self._build_data[build_id]

    def getTaskResult(self, task_id):
        task_id = int(task_id)
        if task_id not in self._task_results:
            result = self.session.getTaskResult(task_id, raise_fault=False)
            self._task_results[task_id] = result

        return self._task_results[task_id]

    def getBuildTaskId(self, build_id):
        build_id = int(build_id)
        if build_id not in self._build_id_to_build_task_id:
            self.build(build_id)

        return self._build_id_to_build_task_id[build_id]

    def getRecordForBuild(self, build_id_or_nvr, grab_build_task_info=False):
        build_id = self.getBuildId(build_id_or_nvr)
        builddata = self.build(build_id)

        # Useful information but does not include floating tags
        # pullspecs = builddata['extra']['image']['index']['pull']
        # tags = builddata['extra']['image']['index']['tags']

        build_task_id = self.getBuildTaskId(build_id)

        # tags from builddata will be only non floating tags
        # pullsepcs from builddata will only be main :{ver}-{rel}
        ret_data = {
            'package_name': builddata['package_name'],
            'nvr': builddata['nvr'],
            'build_id': builddata['id'],
            'build_pullspecs': builddata['extra']['image']['index']['pull'],
            'build_tags': builddata['extra']['image']['index']['tags'],
        }
        if build_id in self._build_id_to_parent_id:
            ret_data['parent_build_id'] = self._build_id_to_parent_id[build_id]

        if grab_build_task_info:
            task_results = self.getTaskResult(build_task_id)

            if 'repositories' in task_results:
                ret_data['task_pullspecs'] = task_results['repositories']

        return ret_data

    def get_container_builds_from_koji_tag(self, koji_tag, get_extra_info=False):
        matching_containers = {}

        for build in koji_tag.builds():
            if build['nvr'] not in self._nvr_to_build_id:
                self._nvr_to_build_id[build['nvr']] = build['id']

            component = build['package_name']

            if component not in matching_containers:
                matching_containers[component] = {}

            record = self.getRecordForBuild(build['id'], grab_build_task_info=get_extra_info)
            matching_containers[component][build['id']] = record

            if 'parent_build_id' in record and False:
                parent_record = self.getRecordForBuild(record['parent_build_id'])
                parent_component = parent_record['package_name']
                if 'openstack' in parent_component:
                    if parent_component not in matching_containers:
                        matching_containers[parent_component] = {}
                    matching_containers[parent_component][parent_record['build_id']] = parent_record

        return matching_containers

    def get_tree(self, list_of_nvrs):
        container_set = set()
        tree = {}
        queue = []
        queue.extend(list_of_nvrs)
        while queue:
            nvr = self.get_nvr(queue.pop())
            build_id = self.getBuildId(nvr)
            parent_build_id = self.getParentBuildId(nvr)
            if parent_build_id is not None and parent_build_id not in tree:
                queue.append(parent_build_id)

            if parent_build_id is not None:
                container_set.add(parent_build_id)
            container_set.add(build_id)
            tree[build_id] = parent_build_id

        for build_id in container_set:
            print("{0} [label = {1} ];".format(build_id, self.get_nvr(build_id)))

        for build_id, parent_build_id in tree.items():
            if parent_build_id is not None:
                print("{0} -> {1} ;".format(parent_build_id, build_id))

        return tree


if __name__ == '__main__':

    import container_processing.caching_koji
    zz = container_processing.caching_koji.CachingKojiWrapper(profile='brew')
    zz.load_cache(debug=True)

    foo = zz.get_list_containers(14.0, 7, latest=True)
    zz.get_tree(foo)

    zz.save_cache(debug=True)
