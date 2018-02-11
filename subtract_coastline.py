import psycopg2
import psycopg2.extras

SQL = """
CREATE TABLE deep_water_areas_subtracted
(
    gid SERIAL NOT NULL,
    elev integer NOT NULL,
    geom geometry(Geometry, 4326),
    CONSTRAINT deep_water_areas_subtracted_pkey PRIMARY KEY (gid)
);
CREATE INDEX deep_water_areas_subtracted_geom_idx ON deep_water_areas_subtracted USING gist(geom);
"""


def prepareTable(conn):
    cur = conn.cursor()
    cur.execute("""
    DROP TABLE IF EXISTS deep_water_areas_subtracted
    """)
    conn.commit()

    cur.execute(SQL)
    conn.commit()

    cur.close()


def getAllAreaIds(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
    SELECT gid FROM deep_water_areas
    """)
    rows = cur.fetchall()
    cur.close()

    return map(lambda row: row['gid'], rows)


def subtract(conn, areaId):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO deep_water_areas_subtracted (elev, geom) (
        SELECT
            a.elev,
            ST_Intersection(
                a.geom,
                (SELECT geom FROM water_polygon_cyclades)
            )
        FROM (
            SELECT gid, elev, geom FROM deep_water_areas WHERE gid=%s
        ) AS a
    )
    """, [areaId])
    conn.commit()
    cur.close()


def main():
    conn = psycopg2.connect('dbname=pocketsail user=postgres password=password')

    prepareTable(conn)

    areaIds = getAllAreaIds(conn)
    print 'Subtracting', len(areaIds), 'areas'

    for areaId in areaIds:
        print areaId
        subtract(conn, areaId)

    conn.close()


if __name__ == '__main__':
    main()
