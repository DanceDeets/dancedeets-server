#!/bin/bash

set -e

BASE_DIR=$(pwd)

TMP_DIR=/tmp/dancedeets-download/
mkdir -p $TMP_DIR

cd $TMP_DIR
curl https://bootstrap.pypa.io/get-pip.py --output $TMP_DIR/get-pip.py
sudo python $TMP_DIR/get-pip.py

# For testing, just install them locally. Depends on pip being installed.
sudo pip install nosegae nose webtest --upgrade --ignore-installed six --user

# TOO OLD, broken media upload: pip install --upgrade -t $BASE_DIR/lib twitter

pip install --upgrade -t $BASE_DIR/lib \
  hubstorage \
  iso3166 \
  oauth2 \
  twilio \
  python-gcm \
  google-api-python-client \
  gdata \
  python-gflags \
  Flask \
  wtforms \
  GoogleAppEngineCloudStorageClient \
  GoogleAppEnginePipeline \
  Graphy \
  simplejson \
  mock \
  mox

pip install --upgrade -t $BASE_DIR/lib dateparser ics

# Install jinja2 library directly, so nlp/ libraries can be used directly
pip install jinja2

# This does not install the static files correctly, since they are not in setup.py
#  GoogleAppEngineMapReduce
# So instead, let's install the depencies manually (listed above):
#  GoogleAppEngineCloudStorageClient \
#  GoogleAppEnginePipeline \
#  Graphy \
#  simplejson \
#  mock \
#  mox
# We re-list them down here, since we can't stick comments inside of the \-joined command above.

function install-git() {
	cd $TMP_DIR
	REPO_PATH=$1
	shift
	echo
	echo $REPO_PATH
	echo
	REPO_FILENAME=$(basename $REPO_PATH)
	REPO_DIRNAME="${REPO_FILENAME%.*}"
	[ -e $REPO_DIRNAME ] || git clone $REPO_PATH
	cd $REPO_DIRNAME
	git pull
	[ -e setup.py ] && python setup.py build
	for MODULE in $*
	do
		[ -h $BASE_DIR/$(basename $MODULE) ] && rm $BASE_DIR/$(basename $MODULE)
		cp -Rf $MODULE $BASE_DIR/lib/
	done
}

# Because the current published version has a bug with media uploads
install-git https://github.com/sixohsix/twitter.git twitter

# Because the published version doesn't work with JsonProperty:
# https://github.com/wtforms/wtforms-appengine/pull/11
install-git https://github.com/mikelambert/wtforms-appengine wtforms_appengine

# Because the published version doesn't install static files with a pip install
install-git https://github.com/GoogleCloudPlatform/appengine-mapreduce.git python/src/mapreduce

