# Changelog

## Next release

* new feature:
  * dubious objects are split into several categories
  * treat `highway=platform` objects without `public_transport=platform` and without any related public transport objects as dubious objects
* algorithm changes:
  * ignore objects with lifecycle prefixes
* bug fixes:
  * only show relevant modalities for plole-only stops if plole also appears in stops with stop position
  * make additional platform-only plole if pole does not cover all modalities of a platform
  * if pole matches multiple platforms, choose the match with highest score instead of by chance
  * take care of multiple values for `ref:IFOPT`
  * do not handle `amenity=ferry_terminal` objects as stop positions if they have `public_transport=station`

## Release 2025-03-09

* new features:
  * button centering the map at your location
  * CSV export of stop locations, stop modalities, stop components (OSM object IDs) for bulk download
  * CSV export of statistics on number of stops and stop components
  * CSV and HTML export of statistics for all regions and their parent regions
  * more details in global log file if processing a region fails
  * keep global log file from previous run
  * relax string matching for `name` and `ref_name` (ignore non-word characters)
* algorithm changes:
  * for ploles with platform and pole increase influence of pole on stop position matching (improves matching results for very long platforms with correct stop position far away from pole; improves matching results for pairs of parallel platforms with two stop positions in between)
* bug fixes:
  * better layout for mobile devices
  * color of stops with components having comments/warnings now is yellow/red
  * keep old plole details files if processing a region fails
  * allow ways with `motor_vehicle=yes` or `motor_vehicle:conditional=*` for bus/trolleybus/share_taxi 
  * improve visibility of dubious ways and relations
  * visibility of platforms/poles/stop positions follows modality of stops they belong to (instead of their own modality)
  * create plole-only stop, if plole has a modality not covered by matching stopos
  * Carto rendering of stop-position-only stops with bus symbol is "good" instead of "missplaced bus symbol"
  * devide Germany into smaller regions (federal states) to reduce size of Overpass queries
  * allow for larger Overpass queries
