import json
import re
import time

import pandas as pd
import geopandas

import geojson
from shapely.geometry import shape, Point

import folium
from folium import plugins
import matplotlib.pyplot as plt


def test_func():
    return "Testing, 1, 2, 3"



def parse_package_search_result(result):
    """
    ### Query the IOOS Catalog CKAN API and perform some analysis:

    Basic workflow:
    - generate a query to pass via ckanapi
    - parse results into a Pandas DataFrame for analysis
    - create a GeoPandas GeoDataFrame to create some maps

    First, we make a function that can parse the CKAN API `package_search` JSON results list into a Python dict with attributes of interest.

    This can then be used to create a Pandas dataframe for further analysis.  Fields from result items currently parsed in `parse_result`:

    ```
    # First-level properties:
    metadata_created
    metadata_modified
    name
    notes
    num_resources
    num_tags
    title

    # Other:
    organization -> title
    organization -> image_url
    organization -> description

    # Extras:
    bbox-east-long
    bbox-west-long
    bbox-north-lat
    bbox-south-lat

    cf_standard_names
    contact-email
    contributor_email
    contributor_name
    contributor_role
    contributor_url

    creator_country
    creator_email
    creator_name
    creator_sector
    creator_url

    distributor-info
    dataset-reference-date
    gcmd_keywords
    gts_ingest
    ioos_ingest
    infoUrl
    instrument
    license

    metadata-date
    name

    platform
    platform_id
    platform_name
    platform_vocabulary

    publisher_country
    publisher_email
    publisher_name
    publisher_url

    resource-type
    responsible-organization
    responsible-parties

    spatial
    spatial-data-service-type
    spatial-reference-system

    standard_name_vocabulary

    temporal-extent-begin
    temporal-extent-end
    temporal_start
    temporal_end

    use-constraints
    use-limitations

    vertical_max
    vertical_min

    waf_location
    harvest_source_title
    ```
    """

    result_dict = {}

    # create lists of data fields from the result dict that we want to parse:
    #    extras_keys: key values of dataset 'extras' dicts
    #    first_level_props: first level keys in the result dict
    extras_keys = ['bbox-east-long','bbox-west-long','bbox-north-lat','bbox-south-lat','cf_standard_names','contact-email','contributor_email', \
                   'contributor_name','contributor_role','contributor_url', 'creator_country','creator_email','creator_name','creator_sector', \
                   'creator_url','dataset-reference-date','distributor-info','gcmd_keywords','gts_ingest','ioos_ingest','infoUrl','instrument', \
                   'license','metadata-date','name','platform','platform_id','platform_name','platform_vocabulary','publisher_country','publisher_email', \
                   'publisher_name','publisher_url','responsible-organization','responsible-parties','resource-type','spatial', \
                   'spatial-data-service-type','spatial-reference-system','standard_name_vocabulary', 'temporal-extent-begin','temporal-extent-end', \
                   'temporal_start','temporal_end','use-constraints','use-limitations','vertical_max', 'vertical_min','waf_location','harvest_source_title']

    first_level_props = ['metadata_created','metadata_modified','name','notes','num_resources','num_tags','title']

    # parse:
    # for extras, we have to scan the list of extras dict items to see if one with a matching key value is found:
    for extra in result['extras']:
        if extra['key'] in extras_keys:
            result_dict[extra['key']] = extra['value']
        # this would add in all the extra['key'] fields into the dict, which isn't necessary:
        #else: result_dict[extra['key']] = None

    #print(result_dict.keys())
    # add any fields not found in extra['key'] as None to ensure no missing fields in dict/DataFrame
    for key in extras_keys:
        if key not in result_dict.keys():
            result_dict[key] = None

    # for first-level properties, just assign the value to result_dict:
    for prop in first_level_props:
         result_dict[prop] = result[prop]

    # special cases - extract organization -> title, image_url, description:
    result_dict['organization-title'] = result['organization']['title']
    result_dict['organization-image_url'] = result['organization']['image_url']
    result_dict['organization-description'] = result['organization']['description']

    return result_dict


def query_ckan(ckanapi, sel_cf_std_name=None, sel_organization=None, sel_format=None):
    """
    #### Submit a query to the CKAN API with parameters of interest

    Take the parameters passed and generate a `ckanapi` query to `package_search` and parse results using `parse_result`

    Returns:

        list_of_datasets: the full list of representations of CKAN datasets accoring to how defined in `parse_result`.
    """
    result_rows = 50
    result_count = 0
    max_results = 5000
    list_of_datasets = []
    datasets_dict = {}

    #print(f"sel_cf_std_name: {sel_cf_std_name}")
    #print(f"sel_organization: {sel_organization}")
    #print(f"sel_format: {sel_format}")

    q = ""
    q = q + f" +organization:{sel_organization}" if sel_organization is not None else q
    q = q + f" +res_format:{sel_format}" if sel_format is not None else q
    print(f"q: {q}")

    fq = ""
    fq = fq + f" +cf_standard_names:{sel_cf_std_name}" if sel_cf_std_name is not None else fq
    print(f"fq: {fq}")

    while True:
        datasets = ckanapi.action.package_search(q=q, fq=fq, rows=result_rows, start=result_count)
        num_results = datasets['count']
        print(f"num_results: {num_results}, result_count: {result_count}")

        # let's add a check to avoid processing too many results:
        if num_results > max_results:
            print(f"Your query returned > {max_results} results.  Try adjusting the parameters to be more selective - the IOOS Catalog server will thank you.")
            break

        # if we return a large number of results (max_results/2), adjust the result_rows value higher to reduce roundtrips:
        if num_results > max_results / 2:
            result_rows = max_results / 10
        elif num_results > max_results / 5:
            result_rows = max_results / 25

        for dataset in datasets['results']:
            datasets_dict = parse_package_search_result(dataset)
            list_of_datasets.append(datasets_dict)
            result_count = result_count + 1
        time.sleep(1)
        if(result_count >= num_results):
            print(f"num_results: {num_results}, result_count: {result_count}")
            break

    # output datasets_dict.keys() and an example dataset:
    print(f"datasets_dict_keys: {datasets_dict.keys()}")
    #if len(list_of_datasets) > 0: [print(key,':',value) for key, value in list_of_datasets[0].items()]
    #if len(list_of_datasets) > 0: print(json.dumps(list_of_datasets[0], indent=4))

    return list_of_datasets


def create_geodataframe(list_of_datasets):
    """
    #### Convert the GeoJSON 'spatial' column to Shapely geometry object to use with GeoPandas

    Resulting fields/columns:
    - 'spatial': Shapely Polygon
    - 'spatial_point': Shapely Polygon and Point (depending on the size of the original polygon bounding box)
    - 'spatial_geojson': GeoJSON text field, the original 'spatial' field value from CKAN API

    WKT is supposed to work according to the [docs](https://geopandas.org/gallery/create_geopandas_from_pandas.html), but seems to fail.

    Returns:

        gdf: GeoPandas DataFrame
    """

    #df = pd.DataFrame(list_of_datasets).dropna(subset=[df.spatial])
    df = pd.DataFrame(list_of_datasets)
    df.dropna(subset=['spatial'], inplace=True)

    # create a new column to store the original 'spatial' column (which is GeoJSON format):
    df['spatial_geojson'] = df.spatial

    # convert the 'spatial' column from GeoJSON to Shapely geometry for GeoPandas compatibility:
    df.spatial = df.spatial.apply(lambda x: shape(geojson.loads(x)))



    # Create a new 'spatial_point' column of Shapely geometry objects that converts any geometries where the difference between lat/lon min and max is < .0001 degree to Point, and retains all the others as Polygon:

    # the approach below uses abs() account for postive/negative lat/lon coordinates to perform the calculation correctly for all quadrants on the globe (or for features crossing meridian/equator)
    df['spatial_point'] = df.apply(lambda row: row.spatial if abs(abs(float(row['bbox-west-long'])) - abs(float(row['bbox-east-long']))) > 0.0001 and abs(abs(float(row['bbox-north-lat'])) - abs(float(row['bbox-south-lat']))) > 0.0001 else Point(float(row['bbox-east-long']), float(row['bbox-south-lat'])), axis=1)

    # same as above but without using abs():
    #df['spatial_point'] = df.apply(lambda row: row.spatial if float(row['bbox-east-long']) - float(row['bbox-west-long']) > 0.0001 and float(row['bbox-north-lat']) - float(row['bbox-south-lat']) > 0.0001 else Point(float(row['bbox-east-long']), float(row['bbox-south-lat'])), axis=1)

    # this just converts every tow to a Point object:
    #df['#spatial_point'] = df.apply(lambda row: Point(float(row['bbox-east-long']), float(row['bbox-south-lat'])), axis=1)


    # GeoPandas GeoDataFrame:
    # Create a GeoPandas GeoDataFrame from the regular Pandas DataFrame.  Assign geometry column.
    gdf = geopandas.GeoDataFrame(df)
    #gdf.set_geometry("spatial", inplace=True, crs="EPSG:4326")
    gdf.set_geometry("spatial_point", inplace=True, crs="EPSG:4326")

    # print the name of the GeoPandas geometry column name:
    print(gdf.geometry.name)

    return gdf


def plot(gdf, sel_cf_std_name=None, sel_organization=None, sel_format=None, sel_plot_type=None):
    """
    Create a plot depending on the sel_plot_type passed.

    Returns:
        ?
    """


    if sel_plot_type == "Static Map":
        world = geopandas.read_file(geopandas.datasets.get_path('naturalearth_lowres'))

        fig, ax = plt.subplots(figsize=(24,18))
        world.plot(ax=ax, alpha=0.4, color='grey')
        #gdf.plot(column='spatial', ax=ax, legend=True)
        gdf.plot(ax=ax, column='creator_sector', legend=True)
        plt.title(f"IOOS Catalog Dataset Coverage.  Filters - CF Std Name: {sel_cf_std_name}, Org: {sel_organization}, Format: {sel_format}")
        return plt


    elif sel_plot_type == "Heat Map":
        map = folium.Map(location = [15,30], tiles='Cartodb dark_matter', zoom_start = 2)

        heat_data = [[geom.xy[1][0], geom.xy[0][0]] if geom.geom_type == "Point" else [geom.centroid.xy[1][0], geom.centroid.xy[0][0]] for geom in gdf.geometry ]

        #heat_data
        plugins.HeatMap(heat_data).add_to(map)
        return map
