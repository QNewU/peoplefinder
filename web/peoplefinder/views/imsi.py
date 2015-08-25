# -*- coding: utf-8 -*-
from datetime import datetime
from pyramid.view import view_config
from sqlalchemy import func

import time
import xmlrpclib
import socket

from model.models import (
    DBSession,
    Measure,
)

from model.hlr import (
    HLRDBSession,
    Sms,
    Subscriber,
)


@view_config(route_name='get_imsi_list', request_method='GET', renderer='json')
def get_imsi_list(request):
    result = []
    messages = []

    query = DBSession.query(
        Measure.id,
        Measure.imsi,
        func.max(Measure.timestamp).label('last')
    ).group_by(Measure.imsi).all()

    for measure in query:
        dtime = datetime.now() - measure.last
        result.append({
            'id': measure.id,
            'imsi': measure.imsi,
            'last_lur': dtime.total_seconds() // 60
        })


    # Calculate message count for each IMSI
    imsi_list = map(lambda item: item['imsi'], result);
    query = HLRDBSession.query(
        Subscriber.imsi,
        func.count(Sms.id).label('sms_count')
    ).filter((
        (Sms.src_addr == Subscriber.extension) |
        (Sms.dest_addr == Subscriber.extension)) &
        (Sms.protocol_id != 64) &
        (Subscriber.imsi.in_(imsi_list))
    ).group_by(
        Subscriber.imsi
    ).all()

    for record in query:
        messages.append({
            'imsi': int(record.imsi),
            'count': record.sms_count
        })


    if 'jtSorting' in request.GET:
        sorting_params = request.GET['jtSorting'].split(' ')
        sorting_field = sorting_params[0]
        reverse = sorting_params[1] == 'DESC'
        result.sort(key=lambda x: x[sorting_field], reverse=reverse)

    return {
        'Result': 'OK',
        'Records': result,
        'Messages': messages
    }


@view_config(route_name='get_imsi_messages', request_method='GET', renderer='json')
def get_imsi_messages(request):
    imsi = int(request.matchdict['imsi'])
    ts_begin = request.GET.get('timestamp_begin')
    ts_end = request.GET.get('timestamp_end')

    pfnum = request.xmlrpc.get_peoplefinder_number()
    query = HLRDBSession.query(
        Sms.id,
        Sms.text,
        Sms.src_addr,
        Sms.dest_addr,
        Sms.created,
        Sms.sent
    ).filter(
        (((Sms.src_addr == Subscriber.extension) & (Sms.dest_addr == pfnum)) |
         ((Sms.dest_addr == Subscriber.extension) & (Sms.src_addr == pfnum))) &
        (Subscriber.imsi == imsi) &
        (Sms.protocol_id != 64)
    )

    result = {
        'imsi': imsi,
        'sms': []
    }

    for obj in query.all():
        sms = {'id': obj.id}
        direction = 'from' if obj.dest_addr == pfnum else 'to'

        if direction == 'to':
            sms['sent'] = True if obj.sent else False

        if ts_begin is not None:
            tsb = datetime.fromtimestamp(float(ts_begin) / 1000)
        if ts_end is not None:
            tse = datetime.fromtimestamp(float(ts_end) / 1000)

        if ts_begin is not None and ts_end is not None:
            if obj.created >= tsb and obj.created <= tse:
                sms['text'] = obj.text
                sms['type'] = direction
        elif ts_begin is None and ts_end is not None:
            if obj.created <= tse:
                sms['text'] = obj.text
                sms['type'] = direction
        elif ts_begin is None and ts_ens is None:
            pass

        result['sms'].append(sms)

    return result


@view_config(route_name='get_imsi_circles', request_method='GET', renderer='json')
def get_imsi_circles(request):
    imsi = request.matchdict['imsi']
    ts_begin = request.GET.get('timestamp_begin')
    ts_end = request.GET.get('timestamp_end')

    query = DBSession.query(
        Measure.distance,
        Measure.gps_lat,
        Measure.gps_lon,
        Measure.timestamp
    ).filter(
        (Measure.imsi == imsi) &
        (Measure.gps_lat != None) &
        (Measure.gps_lon != None) &
        (Measure.timestamp <= datetime.fromtimestamp(float(ts_end) / 1000))
    )

    if ts_begin is not None:
        query = query.filter(
            Measure.timestamp >= datetime.fromtimestamp(float(ts_begin) / 1000)
        )

    result = {
        'imsi': imsi,
        'circles': []
    }

    for circle in query.all():
        result['circles'].append({
            'center': [
                circle.gps_lat,
                circle.gps_lon
            ],
            'radius': circle.distance,
            'ts': time.mktime(circle.timestamp.timetuple())
        })

    return result


@view_config(route_name='send_imsi_message', request_method='POST', renderer='json')
def send_imsi_message(request):
    result = {}
    imsi = request.matchdict['imsi']
    text = request.body

    try:
        sent = request.xmlrpc.send_sms(imsi, text)
        result['status'] = 'sent' if sent else 'failed'
    except (socket.error, xmlrpclib.Error) as e:
        result['status'] = 'failed'
        result['reason'] = e.strerror
    return result


@view_config(route_name='start_tracking', request_method='GET', renderer='json')
def start_tracking(request):
    result = {}
    try:
        request.xmlrpc.start_tracking()
        result['status'] = 'started'
    except (socket.error, xmlrpclib.Error) as e:
        result['status'] = 'failed'
        result['reason'] = e.strerror
    return result


@view_config(route_name='stop_tracking', request_method='GET', renderer='json')
def stop_tracking(request):
    result = {}
    try:
        request.xmlrpc.stop_tracking()
        result['status'] = 'stopped'
    except (socket.error, xmlrpclib.Error) as e:
        result['status'] = 'failed'
        result['reason'] = e.strerror
    return result
