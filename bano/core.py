#!/usr/bin/env python
# coding: UTF-8

import os,os.path
import re
import sys
import time
import xml.etree.ElementTree as ET

from . import constants, db
from . import helpers as hp
from . import db_helpers as dbhp
from .models import Adresse, Adresses, Node, Pg_hsnr
from .outils_de_gestion import batch_start_log
from .outils_de_gestion import batch_end_log
# from .outils_de_gestion import age_etape_dept
from .sources import fantoir

os.umask(0000)


def add_fantoir_to_hsnr():
    for v in adresses:
        if v in fantoir.mapping.fantoir:
            adresses[v]['fantoirs']['FANTOIR'] = fantoir.mapping.fantoir[v]
            adresses[v]['voies']['FANTOIR'] = fantoir.mapping.code_fantoir_vers_nom_fantoir[fantoir.mapping.fantoir[v]]
        else:
            if 'OSM' in adresses[v]['fantoirs']:
                if adresses[v]['fantoirs']['OSM'] in fantoir.mapping.code_fantoir_vers_nom_fantoir:
                    adresses[v]['voies']['FANTOIR'] = fantoir.mapping.code_fantoir_vers_nom_fantoir[adresses[v]['fantoirs']['OSM']]

def append_suffixe(name,suffixe):
    res = name
    if suffixe:
        name_norm = hp.normalize(name)
        suffixe_norm = hp.normalize(suffixe)
        ln = len(name_norm)
        ls = len(suffixe)
        if ln > ls:
            if name[-ls:] != suffixe:
                res = name+' '+suffixe
        else:
            res = name+' '+suffixe
    return res

def get_code_cadastre_from_insee(insee):
    str_query = 'SELECT cadastre_com FROM code_cadastre WHERE insee_com = \'{:s}\';'.format(insee)
    code_cadastre = []
    cur = db.bano.cursor()
    cur.execute(str_query)
    for c in cur:
        code_cadastre = c[0]
    cur.close()
    return code_cadastre

def get_last_base_update(query_name,insee_com):
    resp = 0
    str_query = "SELECT timestamp_maj FROM {} WHERE insee_com = '{}' LIMIT 1;".format(query_name,insee_com)
    cur = db.bano.cursor()
    cur.execute(str_query)
    for l in cur :
        resp = l[0]
    if resp == 0 :
        etape_dept = 'cache_dept_'+query_name
        if dbhp.age_etape_dept(etape_dept,get_short_code_dept_from_insee(insee_com))  < 3600 :
            resp = round(time.time())
    cur.close()
    return resp

def get_data_from_pg(query_name,insee_com):
    # current_time = round(time.time())
    cur_cache = db.bano_cache.cursor()
    str_query = "DELETE FROM {} WHERE insee_com = '{}';".format(query_name,insee_com)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'sql/{:s}.sql'.format(query_name)),'r') as fq:
        str_query+=fq.read().replace('__com__',insee_com)
    # cur_cache.execute(str_query)

    str_query+= "SELECT * FROM {} WHERE insee_com = '{}';".format(query_name,insee_com)
    cur_cache.execute(str_query)

    res = []
    for l in cur_cache :
        res.append(list(l))
    cur_cache.close()
    return res

def get_tags(xmlo):
    dtags = {}
    for tg in xmlo.iter('tag'):
        dtags[tg.get('k')] = tg.get('v')
    return dtags

def has_addreses_with_suffix(insee):
    res = False
    str_query = 'SELECT count(*) FROM suffixe where insee_com = \'{:s}\';'.format(insee)
    cur = db.bano.cursor()
    cur.execute(str_query)
    for c in cur:
        if c[0]> 0 :
            res = True
    cur.close()
    return res

def load_cadastre_hsnr(code_insee):
    dict_node_relations = {}
    destinations_principales_retenues = 'habitation commerce industrie tourisme'
    str_query = "SELECT * FROM bal_cadastre WHERE commune_code = '{}';".format(code_insee)
    cur = db.bano_cache.cursor()
    cur.execute(str_query)
    for cle_interop, ui_adresse, numero, suffixe, pseudo_adresse, name, voie_code, code_postal, libelle_acheminement, destination_principale, commune_code, commune_nom, source, lon, lat, *others in cur:
        housenumber = numero+((' '+suffixe) if suffixe else '')
        if len(name) < 2:
            continue
        if not lon :
            continue
        if pseudo_adresse == 'true':
            continue
        if not re.search(destination_principale,destinations_principales_retenues):
            continue
        adresses.register(name)
        
        if not cle_interop in dict_node_relations:
            dict_node_relations[cle_interop] = []
            dict_node_relations[cle_interop].append(hp.normalize(name))
        if hp.is_valid_housenumber(housenumber):
            nd = Node({'id':cle_interop,'lon':lon,'lat':lat},{})
            adresses.add_adresse(Adresse(nd,housenumber,name,'',code_postal), 'CADASTRE')
    cur.close()

def load_bases_adresses_locales_hsnr(code_insee):
    dict_node_relations = {}
    str_query = "SELECT cle_interop,TRIM (BOTH FROM (numero||' '||suffixe)), voie_nom, long, lat FROM bal_locales WHERE commune_code = '{}';".format(code_insee)
    cur = db.bano_cache.cursor()
    cur.execute(str_query)
    for cle_interop, housenumber, name, lon, lat in cur:
        if len(name) < 2:
            continue
        if not lon :
            continue
        adresses.register(name)
        if not cle_interop in dict_node_relations:
            dict_node_relations[cle_interop] = []
            dict_node_relations[cle_interop].append(hp.normalize(name))
        if hp.is_valid_housenumber(housenumber):
            nd = Node({'id':cle_interop,'lon':lon,'lat':lat},{})
            adresses.add_adresse(Adresse(nd,housenumber,name,'',''), 'BAL')
    cur.close()

def load_hsnr_bbox_from_pg_osm(insee_com):
    # data = get_data_from_pg_direct('hsnr_bbox_insee',insee_com)
    data = get_data_from_pg('hsnr_bbox_insee',insee_com)
    for l in data:
        oa = Pg_hsnr(l, insee_com)
        n = Node({'id':oa.osm_id,'lon':oa.x,'lat':oa.y},{})
        if oa.voie == None:
            continue
        if oa.fantoir == '':
            continue
        adresses.register(oa.voie)
        adresses.add_adresse(Adresse(n,oa.numero,oa.voie,oa.fantoir,oa.code_postal), 'OSM')

def load_hsnr_from_pg_osm(insee_com):
    # data = get_data_from_pg_direct('hsnr_insee', insee_com)
    data = get_data_from_pg('hsnr_insee', insee_com)
    for l in data:
        oa = Pg_hsnr(l, insee_com)
        n = Node({'id':oa.osm_id,'lon':oa.x,'lat':oa.y},{})
        if oa.voie == None:
            continue
        adresses.register(oa.voie)
        adresses.add_adresse(Adresse(n,oa.numero,oa.voie,oa.fantoir,oa.code_postal), 'OSM')

def load_highways_bbox_from_pg_osm(insee_com):
    data = get_data_from_pg('highway_suffixe_insee',insee_com)
    for name, fantoir_unique, fantoir_gauche, fantoir_droit, suffixe, *others in data:
        if fantoir_unique and hp.is_valid_fantoir(fantoir_unique, insee_com):
            code_fantoir = fantoir_unique
        elif fantoir_gauche and hp.is_valid_fantoir(fantoir_gauche, insee_com):
            code_fantoir = fantoir_gauche
        elif fantoir_droit and hp.is_valid_fantoir(fantoir_droit, insee_com):
            code_fantoir = fantoir_droit
        else:
            continue
        if len(name) < 2:
            continue
        name_suffixe = append_suffixe(name,suffixe)
        adresses.register(name_suffixe)
        cle = hp.normalize(name_suffixe)
        if adresses.has_already_fantoir(cle,'OSM'):
            continue
        adresses.add_fantoir(cle,code_fantoir,'OSM')

def load_highways_from_pg_osm(insee_com):
    data = get_data_from_pg('highway_suffixe_insee',insee_com)
    for name, fantoir_unique, fantoir_gauche, fantoir_droit, suffixe, *others in data:
        if len(name) < 2:
            continue
        name_suffixe = append_suffixe(name,suffixe)
        adresses.register(name_suffixe)
        cle = hp.normalize(name_suffixe)
        if adresses.has_already_fantoir(cle,'OSM'):
            continue
        if fantoir_unique and hp.is_valid_fantoir(fantoir_unique, insee_com):
            code_fantoir = fantoir_unique
        elif fantoir_gauche and hp.is_valid_fantoir(fantoir_gauche, insee_com):
            code_fantoir = fantoir_gauche
        elif fantoir_droit and hp.is_valid_fantoir(fantoir_droit, insee_com):
            code_fantoir = fantoir_droit
        else:
            code_fantoir = ''
        if code_fantoir != '':
            adresses.add_fantoir(cle,code_fantoir,'OSM')
            fantoir.mapping.add_fantoir_name(code_fantoir,name_suffixe,'OSM')

def load_highways_relations_bbox_from_pg_osm(code_insee):
    data = get_data_from_pg('highway_relation_suffixe_insee', code_insee) # manque la version bbox
    for name, tags, suffixe, insee, timestamp_maj in data:
        fantoir = ''
        if 'ref:FR:FANTOIR' in tags and hp.is_valid_fantoir(tags['ref:FR:FANTOIR'], code_insee):
            fantoir = tags['ref:FR:FANTOIR']
        else:
            continue
        if len(name) < 2:
            continue
        name_suffixe = append_suffixe(name,suffixe or '')
        adresses.register(name_suffixe)
        cle = hp.normalize(name_suffixe)
        if adresses.has_already_fantoir(cle,'OSM'):
            continue
        adresses.add_voie(name_suffixe,'OSM',name)

def load_highways_relations_from_pg_osm(code_insee):
    data = get_data_from_pg('highway_relation_suffixe_insee', code_insee)
    for name, tags, suffixe, *others in data:
        if len(name) < 2:
            continue
        name_suffixe = append_suffixe(name,suffixe or '')
        adresses.register(name_suffixe)
        cle = hp.normalize(name_suffixe)
        if adresses.has_already_fantoir(cle,'OSM'):
            continue
        if hp.is_valid_fantoir(tags.get('ref:FR:FANTOIR'), code_insee):
            code_fantoir = tags.get('ref:FR:FANTOIR')
        else:
           code_fantoir = ''
        if code_fantoir != '':
            fantoir.mapping.add_fantoir_name(code_fantoir,name,'OSM')

def load_point_par_rue_from_pg_osm(code_insee):
    data = get_data_from_pg('point_par_rue_insee',code_insee)
    for lon, lat, name, *others in data:
        if len(name) < 2:
            continue
        adresses.register(name)
        cle = hp.normalize(name)
        adresses[cle]['point_par_rue'] = [lon, lat]
        if 'OSM' not in adresses[cle]['fantoirs']:
            if cle in fantoir.mapping.fantoir:
                adresses.add_fantoir(cle,fantoir.mapping.fantoir[cle],'OSM')

def load_point_par_rue_complement_from_pg_osm(insee_com):
    data = get_data_from_pg('point_par_rue_complement_insee',insee_com)
    for l in data:
        name = l[2]
        if len(name) < 2:
            continue
        fantoir = l[3]
        if fantoir and fantoir[0:5] != insee_com:
            continue
        if fantoir and len(fantoir) != 10:
            continue
        adresses.register(name)
        cle = hp.normalize(name)
        adresses[cle]['point_par_rue'] = l[0:2]
        if fantoir:
            adresses.add_fantoir(cle,fantoir,'OSM')

def load_type_highway_from_pg_osm(insee_com):
    data = get_data_from_pg('type_highway_insee',insee_com)
    for name, highway_type, *_ in data:
        adresses.register(name)
        cle = hp.normalize(name)
        if highway_type in constants.HIGHWAY_TYPES_INDEX:
            adresses.add_highway_index(cle,constants.HIGHWAY_TYPES_INDEX[highway_type])

# def update_dept_cache(query_name,dept):
#     etape_dept = 'cache_dept_'+query_name
#     print(f"Mise à jour du cache {query_name.upper()}")
#     batch_id = o.batch_start_log(source,etape_dept,dept)
#     with open('sql/{:s}.sql'.format(query_name),'r') as fq:
#         str_query = fq.read().replace(" = '__com__'"," LIKE  '{:s}'".format(hp.get_sql_like_dept_string(dept)))
#         cur_osm_ro = pgcl.cursor()
#         cur_osm_ro.execute(str_query)

#         list_output = list()
#         for lt in cur_osm_ro :
#             list_values = list()
#             for item in list(lt):
#                 if item == None:
#                     list_values.append('null')
#                 elif  type(item) == str :
#                     list_values.append("'{}'".format(item.replace("'","''").replace('"','')))
#                 elif type(item) == list :
#                     if (len(item)) > 0 :
#                         list_values.append("hstore(ARRAY{})".format(str([s.replace("'","''").replace('"','') for s in item])))
#                     else :
#                         list_values.append('null')
#                 else :
#                     list_values.append(str(item))
#             list_values.append(str(current_time))

#             str_values = ','.join(list_values).replace('"',"'")
#             list_output.append(str_values)
#         cur_osm_ro.close()
#         cur_cache_rw = pgcl.cursor()
#         str_query = "DELETE FROM {} WHERE insee_com LIKE '{}';".format(query_name,hp.get_sql_like_dept_string(dept))
#         cur_cache_rw.execute(str_query)
#         if len(list_output) > 0 :
#             str_query = "INSERT INTO {} VALUES ({});COMMIT;".format(query_name,'),('.join(list_output))
#             strq = open('./query.txt','w')
#             strq.write(str_query)
#             strq.close()
#             cur_cache_rw.execute(str_query)
#         cur_cache_rw.close()
#         o.batch_end_log(0,batch_id)

def addr_2_db(code_insee, source, **kwargs):
    global batch_id
    global code_cadastre,code_dept
    global nodes,ways,adresses
    global schema_cible

    schema_cible = 'public'
    if ('SCHEMA_CIBLE' in os.environ) : schema_cible = (os.environ['SCHEMA_CIBLE'])

    debut_total = time.time()
    
    adresses = Adresses(code_insee)

    fantoir.mapping.load(code_insee)

    code_dept = hp.get_code_dept_from_insee(code_insee)

    batch_id = batch_start_log(source,'loadCumul',code_insee)

    if source == 'BAL':
        load_bases_adresses_locales_hsnr(code_insee)
    if source == 'CADASTRE':
        load_cadastre_hsnr(code_insee)
    if source == 'OSM':
        load_hsnr_from_pg_osm(code_insee)
        load_hsnr_bbox_from_pg_osm(code_insee)
        load_type_highway_from_pg_osm(code_insee)
    load_highways_from_pg_osm(code_insee)
    load_highways_relations_from_pg_osm(code_insee)
    load_highways_bbox_from_pg_osm(code_insee)
    load_highways_relations_bbox_from_pg_osm(code_insee)
    add_fantoir_to_hsnr()
    load_point_par_rue_from_pg_osm(code_insee)
    load_point_par_rue_complement_from_pg_osm(code_insee)
    nb_rec = adresses.save(source, code_dept)
    batch_end_log(nb_rec,batch_id)
    fin_total = time.time()

def process(source, code_insee, depts, France, **kwargs):
    liste_codes_insee = []
    if code_insee:
        liste_codes_insee = dbhp.get_insee_name(code_insee)
    if not liste_codes_insee:
        for d in (depts or France):
            liste_codes_insee += dbhp.get_insee_name_list_by_dept(d)
    for code_insee, nom in liste_codes_insee:
        print(f"{code_insee} - {nom}")
        addr_2_db(code_insee, source)