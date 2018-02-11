# Deep water bathymetry (WIP)

## Dependencies

- psycopg2
- gdal_contour

## bboxes used in this example

- DEM       23.95, 38.16, 26.30, 36.01 (ul, lr)
- bathy     23.96, 38.15, 26.29, 36.02 (ul, lr)
- water     23.96, 36.02, 26.29, 38.15 (ll, ur)

## 1. Download Aegean sea DEM

Go to [EMODnet bathymetry portal](http://portal.emodnet-bathymetry.eu),
Download Products, and choose the NetCDF link. For consistency with this
guide unzip the archive as `aegean_dem.mnt`.

## 2. Clip DEM by a bbox (optional)

Clip the DEM by a desired bbox (upper-left, lower-right):

```bash
gdal_translate NETCDF:"aegean_dem.mnt":DEPTH_SMOOTH -projwin 23.95, 38.16, 26.30, 36.01 cyclades_dem.mnt
```

## 3. Extract contour from DEM

```bash
gdal_contour -a elev cyclades_dem.mnt contours/cyclades_contours_200.shp -i 200.0
```

## 4. Upload contours to postgres

```bash
shp2pgsql -I -s 4326 -d contours/cyclades_contours_200.shp public.deep_water_contour_multilines | psql -U postgres -d pocketsail
```

## 5. Convert multitlines to lines

```SQL
SELECT gid, elev, ST_LineMerge(geom) AS geom INTO deep_water_contour_lines FROM deep_water_contour_multilines
```

## 6. Delete contours outside of the bbox

```SQL
DELETE FROM deep_water_contour_lines WHERE ST_Disjoint(geom, ST_MakeEnvelope(23.96, 36.02, 26.29, 38.15, 4326))
```

## 7. Create deep_water_areas table

```SQL
CREATE TABLE deep_water_areas (
    gid SERIAL NOT NULL,
    geom geometry(Polygon, 4326),
    CONSTRAINT deep_water_areas_pkey PRIMARY KEY (gid)
)
```

### Test deep/shallow water

A query to test if the given area is to the left of the contour. For testing
if the area is "deep" I assume that the contours were creates using
`gdal_contour` (or a similar program) that leaves leaves the hill to the
right and the valley to the left of the contour.
[S_OffsetCurve](https://postgis.net/docs/ST_OffsetCurve.html) offsets the
given curve to the left for positive values hence a positive outcome of the
query means that the area is "deep".

**TODO: Simplify by offsetting the whole curve and finding the middle point
of that curve.**

```SQL
SELECT ST_Intersects(
    (SELECT geom FROM <table_with_areas> WHERE gid = <area_gid>),
    d.pt
)
FROM (
    SELECT
        ST_Line_Interpolate_Point(
            ST_OffsetCurve(ST_MakeLine(c.p0, c.p1), 0.0000001), -- a very small number, close to the original curve
            0.5
        ) AS pt
    FROM (
        SELECT
            ST_PointN(b.curve, floor(b.num_vertices / 2)::integer) AS p0,
            ST_PointN(b.curve, floor(b.num_vertices / 2)::integer + 1) AS p1
        FROM (
            SELECT a.curve AS curve, ST_NPoints(a.curve) AS num_vertices FROM (
                SELECT geom AS curve FROM <table_with_contours> WHERE gid = <contour_gid>
            ) AS a
        ) AS b
    ) AS c
) AS d
```
