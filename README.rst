Testing repo for working with container images

the container-processing repo is currently collection of tools/code-snipits that make  it easier to work with a set of container images for OSP  from brew/koji (OSBS) , advisories, CVP or other sources
and creating/updating internal registry tags with those image sets

helpers.py has CachingKojiWrapper class
   which provides caching to speed up processing when interacting with brew/koji container images

update_internal_registry is cli script that generates set of oc (openshift) commands to import-image and tag a set of container images to a tag for CI to work with

group_testing_parse is cli/code for parsing Group Testing UMB message (json blob with set of container images to test with)


goal is to have POC script that can parse Group Testing UMB Message + look at brew/koji container images and generate a set of commands to update
internal registry for a new tag that CI can run against.


