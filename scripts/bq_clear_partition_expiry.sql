ALTER TABLE `project-3c4cd22c-ff1e-405d-803.terrasentinel.timeseries`
SET OPTIONS (partition_expiration_days = NULL);

ALTER TABLE `project-3c4cd22c-ff1e-405d-803.terrasentinel.rain`
SET OPTIONS (partition_expiration_days = NULL);

ALTER TABLE `project-3c4cd22c-ff1e-405d-803.terrasentinel.site_snapshots`
SET OPTIONS (partition_expiration_days = NULL);
