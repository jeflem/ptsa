# Changelog

## Next release (dev branch)

* algorith changes:
  * for ploles with platform and pole increase influence of pole on stop position matching (improves matching results for very long platforms with correct stop position far away from pole; improves matching results for pairs of parallel platforms with two stop positions in between)
* bug fixes:
  * create plole-only stop, if plole has a modality not covered by matching stopos
  * Carto rendering of stop-position-only stops with bus symbol is "good" instead of "missplaced bus symbol"
  * devide Germany into smaller regions (federal states) to reduce size of Overpass queries
  * allow for larger Overpass queries
