# Getting the data

Two registrations. Do the DHS one today because everything waits on it. Earth
Engine can follow.

---

## 1. DHS Program (the blocking one)

### What you are asking for

Household survey microdata plus the GPS coordinates of survey clusters, for The
Gambia and eleven other West African countries. The wealth index in the
household file is your label; the GPS file tells you where each cluster is.
Without both, there is no paper.

### How it works

Access is granted **by country**, not by file. Once a country is approved you
get all its unrestricted datasets. So request every country you might use in one
go, rather than coming back repeatedly. Review takes **24 to 48 hours** on
working days.

GPS data needs one extra thing: a short abstract saying how you will use the
coordinates, and an acknowledgement of the conditions of use. This is the step
people rush and get delayed on.

### Steps

1. Go to <https://dhsprogram.com/data/new-user-registration.cfm> and register.
   Use your KNUST address, `abalisa@st.knust.edu.gh`. An institutional address
   is treated more seriously than a personal one.
2. Create a new research project. You will be asked for a title and a
   description of the analysis. Text for both is below.
3. Select countries. Request all twelve listed below at once.
4. Tick the GPS / geographic datasets option and paste the GPS abstract below.
5. Accept the terms of use.
6. Wait one to two working days for the approval email.

### Countries to request

The Gambia, Senegal, Mali, Nigeria, Ghana, Burkina Faso, Côte d'Ivoire,
Mauritania, Sierra Leone, Guinea, Benin, Togo.

The Gambia is the target. The other eleven are the training set. Request them
all now even if you end up dropping some, because adding a country later means
another approval cycle.

### Project title

> Cross-border calibration of satellite-based poverty estimates in West Africa

### Project description

Paste this, then change anything that does not sound like you.

> Satellite-based models are increasingly used to estimate household wealth in
> countries and years where no household survey exists. These models are
> typically trained and validated on survey clusters from the same countries,
> then applied to countries with no survey at all. Their reported accuracy is
> therefore measured under conditions that do not match how they are used.
>
> This project examines whether the uncertainty such models report remains valid
> when they are applied across a national border. Using DHS cluster-level wealth
> index values from West African surveys, I will train wealth models on publicly
> available geospatial covariates (night-time lights, population density,
> building footprints, road networks, land cover and rainfall) in a set of
> source countries, then evaluate them on The Gambia, which is excluded entirely
> from training and model selection.
>
> The evaluation focuses on calibration rather than accuracy alone. I will
> measure whether prediction intervals estimated within the training countries
> retain their nominal coverage on Gambian clusters, and whether domain
> adaptation methods that improve point accuracy also restore calibration. The
> intended output is a methodological paper on uncertainty quantification under
> geographic distribution shift, submitted to a machine learning workshop and
> released as a preprint.
>
> I am a BSc Statistics student at Kwame Nkrumah University of Science and
> Technology. Analysis will be at cluster level only. No attempt will be made to
> identify individuals or households, and no microdata will be redistributed.

### GPS abstract

> Cluster coordinates are required to extract geospatial covariates for each
> survey cluster. For every cluster I will compute summaries of night-time
> lights, population density, building footprints, road density, land cover and
> rainfall within a buffer around the cluster location.
>
> A buffer rather than a point is used deliberately, because DHS applies random
> displacement of up to 2 km in urban areas and 5 km in rural areas, with 1% of
> rural clusters displaced up to 10 km. Extracting covariates at the recorded
> point would attribute the wrong location to each cluster. Buffer radii will be
> chosen to reflect the published displacement distances.
>
> Coordinates will be used only to link clusters to geospatial covariates. No
> cluster location will be published, mapped at identifying resolution, or
> redistributed. Results will be reported as aggregate model performance
> statistics.

The buffer paragraph is there for a reason. It shows the reviewer you understand
the displacement procedure, which is the main thing that distinguishes someone
who will use GPS data properly from someone who will not.

### What you get

For each country, look for two files:

- **Household Recode (HR)**, usually a Stata `.DTA` file. Contains `hv271`, the
  wealth index factor score, and `hv001`, the cluster number.
- **Geographic Data (GE)**, a shapefile. Contains cluster number, latitude,
  longitude and an urban/rural flag.

You join them on cluster number.

### Terms you are agreeing to

Read them, but the substance is: do not redistribute the microdata, do not try
to identify anyone, use it for the stated project, and cite DHS. Keeping the
repository private is consistent with this. Do not commit any DHS file to git;
the `.gitignore` already excludes `data/raw/`, and it should stay that way.

---

## 2. Google Earth Engine (for Sentinel-2)

Needed only for the satellite imagery composites. Everything else downloads
directly.

1. Sign in at <https://code.earthengine.google.com> with a Google account.
2. Register for non-commercial or academic research use. Earth Engine now
   attaches to a Google Cloud project, so you will be asked to create or select
   one. Choose the free non-commercial option and do not enable billing.
3. Wait for approval, usually a day or two.

Free for research. Verify no card is required at the point you are asked, and
stop if one is.

---

## 3. What needs no registration at all

These download directly and I can start on them immediately:

WorldPop population rasters, VIIRS night-time lights, Google and Microsoft Open
Buildings, OpenStreetMap road networks, CHIRPS rainfall, ESA WorldCover.

This is why the pipeline can be built while your DHS application is in review.

---

## 4. Order of operations

1. DHS registration today. One to two days for approval.
2. Earth Engine registration today as well, since it also involves waiting.
3. While waiting, I build the covariate pipeline on the open sources.
4. When DHS approval arrives, the labels drop into a pipeline that already
   works.

Tell me when each approval lands.
