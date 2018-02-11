import psycopg2
import psycopg2.extras

SQL = """
CREATE TABLE deep_water_areas
(
    gid SERIAL NOT NULL,
    elev integer NOT NULL,
    keep bool DEFAULT NULL,
    geom geometry(Polygon, 4326),
    CONSTRAINT deep_water_areas_pkey PRIMARY KEY (gid)
);
CREATE INDEX deep_water_areas_geom_idx ON deep_water_areas USING gist(geom);
"""


def clearAreas(conn):
    cur = conn.cursor()
    cur.execute("""
    DELETE FROM deep_water_areas
    """)
    conn.commit()
    cur.close()


def loadElevs(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
    SELECT DISTINCT(elev) FROM deep_water_contours ORDER BY elev
    """)
    rows = cur.fetchall()
    cur.close()
    return map(lambda row: int(row['elev']), rows)


def loadContoursIds(conn, elev):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
    SELECT gid FROM deep_water_contours WHERE elev = %s
    """, [elev])
    rows = cur.fetchall()
    cur.close()
    return map(lambda row: int(row['gid']), rows)


def loadIntersectingAreasIds(conn, elev, contourId):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
    SELECT gid
    FROM deep_water_areas
    WHERE elev = %s AND ST_Intersects(geom, (SELECT geom FROM deep_water_contours WHERE gid = %s))
    """, [elev, contourId])
    rows = cur.fetchall()
    cur.close()
    return map(lambda row: int(row['gid']), rows)


def initElevArea(conn, elev):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO deep_water_areas (elev, geom) 
    VALUES (%s, ST_MakeEnvelope(23.96, 36.02, 26.29, 38.15, 4326))
    """, [elev])
    conn.commit()
    cur.close()


def deleteArea(conn, areaId):
    cur = conn.cursor()
    cur.execute("""
    DELETE FROM deep_water_areas WHERE gid = %s
    """, [areaId])
    conn.commit()
    cur.close()


def tidyUp(conn):
    cur = conn.cursor()
    cur.execute("""
    DELETE FROM deep_water_areas WHERE keep=False OR keep IS NULL
    """)
    conn.commit()
    cur.close()


def splitArea(conn, areaId, contourId, elev):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
    INSERT INTO deep_water_areas (geom, elev) (
        SELECT (g.dump).geom, %s FROM (
            SELECT ST_Dump(ST_Split(
                (SELECT geom FROM deep_water_areas WHERE gid = %s),
                (SELECT geom FROM deep_water_contours WHERE gid = %s))
            ) AS dump
        ) AS g
    ) RETURNING gid
    """, [elev, areaId, contourId])
    conn.commit()
    row = cur.fetchall()
    cur.close()

    return map(lambda col: col[0], row)


def isDeep(conn, areaId, contourId):
    cur = conn.cursor()
    cur.execute("""
    SELECT ST_Intersects(
        (SELECT geom FROM deep_water_areas WHERE gid = %s), d.pt)
    FROM (
        SELECT
            ST_Line_Interpolate_Point(ST_OffsetCurve(ST_MakeLine(c.p0, c.p1), 0.0000001), 0.5) AS pt
        FROM (
            SELECT
                ST_PointN(b.curve, floor(b.num_vertices / 2)::integer) AS p0,
                ST_PointN(b.curve, floor(b.num_vertices / 2)::integer + 1) AS p1
            FROM (
                SELECT a.curve AS curve, ST_NPoints(a.curve) AS num_vertices FROM (
                    SELECT geom AS curve FROM deep_water_contours WHERE gid = %s
                ) AS a
            ) AS b
        ) AS c
    ) AS d
    """, [areaId, contourId])
    row = cur.fetchone()
    cur.close()
    return row[0]


def setAreaKeep(conn, areaId, keep):
    cur = conn.cursor()
    cur.execute("""
    UPDATE deep_water_areas SET keep=%s WHERE gid=%s 
    """, [keep, areaId])
    conn.commit()
    cur.close()


def main():
    conn = psycopg2.connect('dbname=pocketsail user=postgres password=password')

    clearAreas(conn)

    elevs = loadElevs(conn)

    for elev in elevs:
        initElevArea(conn, elev)

    for elev in elevs:
        print 'Elev: ', elev

        contourIds = loadContoursIds(conn, elev)
        for contourId in contourIds:
            areasIds = loadIntersectingAreasIds(conn, elev, contourId)
            for areaId in areasIds:
                splitAreaIds = splitArea(conn, areaId, contourId, elev)
                deleteArea(conn, areaId)

                for splitAreaId in splitAreaIds:
                    # test if it's "deep" or "shallow"
                    deep = isDeep(conn, splitAreaId, contourId)
                    if deep:
                        setAreaKeep(conn, splitAreaId, True)
                    else:
                        setAreaKeep(conn, splitAreaId, False)

    tidyUp(conn)

    conn.close()


if __name__ == '__main__':
    main()
