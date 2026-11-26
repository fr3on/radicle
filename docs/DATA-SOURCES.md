# Data sources

Datasets radicle is tested on, what each result shows, and leads that are not used yet. Numbers come from the current code (`radicle reproduce`, `scripts/eval_*.py`) unless marked otherwise.

## Datasets in use

| Dataset | Crop | Licence | Where | Used for |
|---|---|---|---|---|
| [Nile wheat trials](https://odjar.org/article/view/16318) (Kheir, Abdelaal, Hoogenboom, Asseng; ODJAR 2020, DOI 10.18174/odjar.v6i0.16318) | wheat | CC BY 4.0 | `data/external/egypt-nile-wheat/` (committed, 105 KB) | wheat test, CI |
| [USDA-ARS Colorado Maize Water Productivity Dataset 2008-2011](https://catalog.data.gov/dataset/usda-ars-colorado-maize-water-productivity-dataset-2008-2011) (Trout, Ag Data Commons 2016, DOI 10.15482/USDA.ADC/1254006) | maize | public domain | `data/external/greeley-maize/` (git-ignored, 16 MB); two plots committed as `data/greeley-2010-t1`, `-t6` | maize calibration |
| [INVITE European variety trials](https://zenodo.org/records/20786880) | wheat | CC BY 4.0 | `data/external/eu-wheat-vct/x/` (git-ignored, 180 MB) | wheat timing calibration |
| [AGC4 dwarf tomato](https://data.4tu.nl/datasets/fa102772-32db-4b30-bace-12f2016722ce/1) | greenhouse tomato | CC BY 4.0 | `data/external/agc4-dwarf-tomato/x/` (git-ignored, 58 MB) | greenhouse scaffold |

**Getting the git-ignored data**
- Greeley: download these 11 files from the catalog page and rename spaces to underscores: `LIRF Maize 2008..2011.xlsx`, `LIRF Weather 2008..2011.xlsx`, `LIRF Soils.xlsx`, `DataDictionary r1.xlsx`, `LIRF Methodology r1.pdf` (e.g. `LIRF_Maize_2008.xlsx`). Put them in `data/external/greeley-maize/`. Then `python scripts/export_greeley.py` rewrites the two committed plots.
- INVITE: unzip the Zenodo `Dataset.zip` into `data/external/eu-wheat-vct/x/`. It contains Windows executables; they are not used and should not be run.
- AGC4: download only `timeseries.zip` (6 MB) and unzip into `data/external/agc4-dwarf-tomato/x/`. Do not download the 31 GB camera archive.

## Nile wheat (22 fully irrigated plots, 4 sites, one season)
Four sites (Sakha, Menofya, Beni Suef, Aswan) in DSSAT format. Observed means exist for three seasons, but management files only for the first, so 22 treatments (3 cultivars x 2 sowing dates) are usable. The weather has only radiation, Tmax, Tmin and rain: wind (2 m/s) and humidity (dew point = Tmin - 2 C) are assumed in the loader.

| Parameters | Yield sim / obs (t/ha) | RMSE | r | Days to anthesis sim / obs | Days to maturity sim / obs |
|---|---|---|---|---|---|
| `wheat` (placeholder) | 5.84 / 7.37 | 1.65 | 0.50 | 70 / 67 | 125 / 104 |
| `wheat_eu_calibrated` | 4.32 / 7.37 | 3.10 | 0.52 | 88 / 67 | 138 / 104 |

The hottest site (Aswan) is worst (4.6 vs 6.9 t/ha). The European timing calibration does not transfer to Egypt. Caveat: the ADAT and MDAT columns are read as days after planting, which is inferred from the file, not documented; check the article before relying on the timing comparison. Observed yields are research-plot yields, above the 6.4-6.5 t/ha national average.

## Greeley maize (4 years x 6 irrigation levels, 40-100% of ET)
Drip-irrigated maize at 40.45 N, 1425 m, 2008-2011, with daily weather, per-day irrigation, soil water, final biomass and grain yield. Loader: `src/radicle/ingest/greeley.py`.

**Data problems handled by the loader:** one day each in 2009 and 2011 has missing values (filled by interpolation); 2010 has a corrupt row (Tmin -231 C, dropped and filled) and one impossible radiation value (45 MJ/m2/day on 2010-06-12, capped at the clear-sky limit).

**Assumptions not in the data:** irrigation water EC 0.5 dS/m, initial ECe 1.0 dS/m, initial depletion 20%, rooting depth 1.05 m, one soil for all plots (mean pressure-plate water content at 33 and 1500 kPa over 0-100 cm: fc 0.21, wp 0.14).

| Parameters | Yield bias (t/ha) | RMSE | r | Note |
|---|---|---|---|---|
| `maize` (placeholder) | +5.3 | 6.44 | 0.40 | only 18 of 24 runs finish: a 2600-degree-day hybrid never matures at this cool site |
| `maize_greeley` (phenology from 2 observed silking dates) | +5.8 | 5.91 | 0.94 | ranks irrigation levels correctly (r 0.97-0.99 within each year) but overestimates yield |
| calibrated, each year predicted from the other three | -0.3 | 0.96 | 0.91 | records in `docs/maize_calibration.json` |

- **Calibration:** grid search of `wp_g_m2`, `harvest_index` and `p_depletion` on grain yield and final biomass. Fitted `wp_g_m2` was 20 in all four folds (placeholder 33.7). Per-year held-out bias: -0.5, +0.4, -1.4, +0.3 t/ha. `p_depletion` sits at its grid edge (0.4); widen the grid before trusting it. The all-data fit is `params/maize_greeley_calibrated.json`.
- **ET0:** radicle's FAO-56 Penman-Monteith agrees with the station's published ASCE grass ETo over 601 growing-season days (bias -0.13 mm/day, RMSE 0.41, r 0.97).
- **Limits:** one site, four seasons, drip irrigation, no nitrogen, heat or salinity information. The driest plot (3.4 t/ha observed in 2011) is still predicted at 5.3. The fitted water productivity of 20 g/m2 versus about 34 in the literature points to unmodelled losses, not to a real maize value. Salinity is not tested by this dataset.

## New Zealand winter wheat (50 sowing-date and density treatments, 2 sites, 6 seasons)
Plant & Food Research trials at Leeston and Wakanui, 2013-2018, with daily weather (including wind and humidity), soil layers, irrigation events, daily leaf area index and biomass, anthesis and maturity dates, and grain yield. Source: [Harvard Dataverse, doi:10.7910/DVN/XA4VA2](https://doi.org/10.7910/DVN/XA4VA2). Loader: `src/radicle/ingest/nzwheat.py`. Unzip the download to `data/external/nz-wheat/`.

**Licence is unclear:** Dataverse labels it CC0, but the dataset description says use is restricted by a consortium agreement and names Plant & Food Research as the contact. The data is git-ignored and not redistributed. Resolve this before publishing results.

**Assumptions not in the data:** initial depletion 10%, initial ECe 0.5 dS/m, irrigation water EC 0.5 dS/m, rooting depth capped at 1 m. Density is not modelled.

| Parameters | Yield bias (t/ha) | RMSE | r |
|---|---|---|---|
| `wheat` (placeholder) | -0.02 | 2.15 | -0.09 |

- **Reading:** the near-zero bias is chance. The model has no skill across treatments here, and simulated anthesis comes about 125 days earlier than observed. These are long-season crops sown in February to April and harvested the next February, and radicle has no vernalisation or photoperiod response.
- **Use:** a hard test for wheat phenology and the first dataset with measured leaf area and biomass over time.

## INVITE European wheat trials (473 trials: Czech Republic, Hungary, Switzerland)
Rainfed winter wheat, 2003-2018. France is not loaded (weather files map by site code).

- Placeholder parameters: yield 8.68 sim vs 7.32 obs t/ha, RMSE 2.57, r 0.14; simulated anthesis 20.4 days before observed ear emergence; maturity 14.3 days early.
- Timing calibration on 50 trials from years up to 2012, tested on 178 trials from 2013-2018 (figures from an earlier run, before the salt and fungicide fixes; timing is unaffected because phenology did not change): anthesis bias -0.9 days (SD 9.6), maturity bias -1.2 days (SD 9.0). Yield showed no skill (r about 0.05).
- The model has no nitrogen, cultivar or vernalisation effects, which probably drive yield in these trials (untested).
- The model's "anthesis" is fitted to observed ear emergence (heading), which comes several days earlier.
- `wheat_eu_calibrated` is for timing only. The salt, disease and water-productivity values drifted because the data cannot constrain them, and two stage thresholds came out nearly equal (1392 vs 1398), a sign of over-flexible fitting. The provenance labels in the file say this.

## AGC4 dwarf tomato (greenhouse)
Six compartments, 5-minute data (temperature, PAR, CO2, humidity deficit, drain volume and EC) and manual fruit harvests, Bleiswijk (Netherlands). Dwarf tomato in pots, so the wheat soil model does not apply; `models/greenhouse.py` is a light-use-efficiency scaffold.

- Leave-one-compartment-out test (fit light-use efficiency and flowering time on 5 compartments, predict the 6th): relative RMSE of fruit fresh weight 0.26 for the model vs 0.22 for a baseline (mean of the other compartments). With the final harvest excluded (14 observations): 0.20 vs 0.23, not statistically meaningful.
- The data has no record of fruit removals, so picking cannot be modelled; this confounds the comparison. Final harvest dates are assumed to be the last full day of each series.
- Drain EC looks real in only 2 of 6 compartments (about 3.6-3.8 dS/m); the others read about 0. Salinity is not tested.

## Known gaps
- **Salinity:** no bundled dataset tests the salt response. No open Egyptian salinity trial was found. Leads to check for data statements or ask the authors: [saline irrigation 3 and 6 dS/m](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9431559/), [Nile Valley irrigation + HYDRUS-2D](https://link.springer.com/article/10.1007/s44533-026-00026-8), [NE Delta salinity monitoring, EC 0.53-49.7 dS/m](https://www.researchgate.net/publication/385780793_Monitoring_soil_salinization_and_waterlogging_in_the_northeastern_Nile_Delta_linked_to_shallow_saline_groundwater_and_irrigation_water_quality), [East Delta EM38 survey](https://www.researchgate.net/publication/358637412_Mapping_of_Soil_Salinity_Using_Electromagnetic_Induction_A_Case_Study_of_East_Nile_Delta_Egypt). Non-Egyptian example with data: [North China Plain saline irrigation + SALTMED](https://zenodo.org/records/8090804).
- **Nitrogen, vernalisation, heat stress:** missing from the model; the European and Greeley results point to them.
- **Hot, arid conditions:** the Nile set is the only one.

## More datasets (licences checked)
Licences below were read from the publisher or repository record (Crossref, Europe PMC, DataCite). A paper's licence covers the paper; check the data files themselves before redistributing.

| Dataset | Licence | Use |
|---|---|---|
| [AgMIP-Wheat pilot data](https://doi.org/10.17026/dans-zb6-6fvq) (Australia, Netherlands, India, Argentina; includes the Hot Serial Cereal heat experiment; [paper](https://library.wur.nl/ojs/index.php/ODJAR/article/view/14746), [Martre et al. 2018](https://ars.usda.gov/ARSUserFiles/20200500/Pubs%202018/Martre%20et%20al.%20OpenAg2018.pdf)) | CC0 | multi-site wheat phenology and growth |
| [AgMIP high-yielding traits](https://doi.org/10.7910/DVN/VKWKUP) | CC0 | wheat; downloaded as one `.rar`, not opened |
| [Bushland, Texas maize](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11794518/) | CC BY | second maize site with ET, growth and yield |
| [Faba bean and wheat intercropping, Lebanon and Morocco](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8989693/) | CC BY | on-farm trials, Mediterranean |
| [Maize sowing dates and irrigation levels](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10415405/) | CC BY | maize, Egypt |
| [Wheat soil quality, yield and water productivity, Riyadh](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11174773/) | CC BY | wheat, Saudi Arabia |
| [Saline irrigation 3 and 6 dS/m](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9431559/) | CC BY | salinity yield response, Egypt |
| [Wheat drip vs surface irrigation, Agronomy 2022](https://doi.org/10.3390/agronomy12071488) | CC BY | wheat, Saudi Arabia |
| Egyptian wheat papers: [Land 2021 (Sakha 95)](https://doi.org/10.3390/land10121375), [Agronomy 2024 (six cultivars)](https://doi.org/10.3390/agronomy14123057) | CC BY | trial tables; ask the authors for raw data and EC |
| [Greenhouse challenge, lettuce](https://doi.org/10.4121/21960932.v1) | CC BY | greenhouse |
| [Greenhouse challenge, cucumber](https://doi.org/10.4121/uuid:e4987a7b-04dd-4c89-9b18-883aad30ba9a) | CC0 | greenhouse |

**Not confirmed:** the [DSSAT experimental data](https://github.com/DSSAT/dssat-csm-data) repository declares no licence; the [CGIAR winter wheat nurseries](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8844391/) record returned no licence; [SALTMED tomato](https://www.researchgate.net/publication/322194676_Soil_Salinity_and_Tomato_Yield_Simulation_Using_SALTMED_Model_in_Drip_Irrigation) and the [Nile Delta DSSAT-CERES preprint](https://www.researchsquare.com/article/rs-10600368/v1) were not checked. The cherry tomato greenhouse edition and the salinity variables in the greenhouse sets are also unchecked.

**Yield benchmarks (sanity checks, not calibration).** Egypt national wheat yield is about 6.3-6.9 t/ha: [USDA FAS](https://ipad.fas.usda.gov/countrysummary/Default.aspx?id=EG&crop=Wheat), [MDPI 2021](https://www.mdpi.com/2071-1050/11/16/4457) (2000-2020 mean 6.47 t/ha, CC BY), [ICARDA yield-gap study](https://buscador.una.edu.ni/Record/CGSpace159593/Details). Salinity affects roughly 30-35% of Egypt's irrigated land and cuts yields 10-40% ([Ahram](https://english.ahram.org.eg/NewsContent/3/12/562624/Business/Economy/Addressing-soil-salinity-important-to-safeguard-Eg.aspx)). Soil EC in the north-eastern Delta averaged 6.1 dS/m in March and 9.6 in September 2022 ([Abuzaid et al. 2023](https://doi.org/10.3390/su15129440), CC BY, 70 topsoil samples, no crop data).

**Weather.** [Open-Meteo historical API](https://open-meteo.com/en/terms) (from 1940, CC BY 4.0, free tier non-commercial); NASA POWER (terms not checked). Israel: [IMS API](https://ims.gov.il/sites/default/files/2023-01/API_Explanation_en.pdf) (token may be required), [HDX precipitation summaries](https://data.humdata.org/dataset/daily-summaries-of-precipitation-indicators-for-israel). UAE: [NCM station statistics](https://addata.gov.ae/group/national-center-meteorology) (statistics, maybe not daily).

**Gulf and Israel field data:** no open trial datasets found beyond the papers above. Saudi statistics: [GASTAT surveys](https://www.stats.gov.sa/sites/default/files/Agricultural_Production_Survey_Publication_2021_EN_0.pdf), [AlUla open data](https://www.rcu.gov.sa/en/open-data-library/Agriculture-and-Soil-Data), [Estidamah open data](https://estidamah.gov.sa/en/about/e-participation/open-data/Pages/library.aspx), [deficit irrigation, Riyadh](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11174773/).
