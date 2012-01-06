rm bulkloader*
db_names="DBEvent PotentialEvent Source LocationMapping FacebookCachedObject" # GeoCode City"
for name in $db_names ; do
  echo "downloading $name"
  rm local_data/$name-new
  appcfg.py download_data --application=s~dancedeets-hrd --kind="$name" --url=http://dancedeets-hrd.appspot.com/_ah/remote_api --filename=local_data/$name.db-new
  mv local_data/$name.db{-new,}
done
rm bulkloader*
for name in $db_names ; do
  echo "uploading $name"
  #appcfg.py upload_data --application=dancedeets-hrd --kind="$name" --url=http://127.0.0.1:8080/_ah/remote_api --filename=local_data/$name.db
done

