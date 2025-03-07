# Changelog

## Next release (dev branch)

* new features:
  * CSV export of stop locations, stop modalities, stop components (OSM object IDs) for bulk download
  * CSV export of statistics on number of stops and stop components
  * CSV and HTML export of statistics for all regions and their parent regions
  * more details in global log file if processing a region fails
  * relax string matching for `name` and `ref_name` (ignore non-word characters)
* algorithm changes:
  * for ploles with platform and pole increase influence of pole on stop position matching (improves matching results for very long platforms with correct stop position far away from pole; improves matching results for pairs of parallel platforms with two stop positions in between)
* bug fixes:
  * color of stops with components having comments/warnings now is yellow/red
  * keep old plole details files if processing a region fails
  * allow ways with `motor_vehicle=yes` or `motor_vehicle:conditional=*` for bus/trolleybus/share_taxi 
  * improve visibility of dubious ways and relations
  * visibility of platforms/poles/stop positions follows modality of stops they belong to (instead of their own modality)
  * create plole-only stop, if plole has a modality not covered by matching stopos
  * Carto rendering of stop-position-only stops with bus symbol is "good" instead of "missplaced bus symbol"
  * devide Germany into smaller regions (federal states) to reduce size of Overpass queries
  * allow for larger Overpass queries
