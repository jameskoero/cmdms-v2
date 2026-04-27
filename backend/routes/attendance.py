from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Attendance, Member, SERVICE_TYPES
from datetime import date, datetime
from sqlalchemy import func

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/', methods=['GET'])
@jwt_required()
def get_attendance():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    member_id = request.args.get('member_id', type=int)
    service_type = request.args.get('service_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = Attendance.query

    if member_id:
        query = query.filter_by(member_id=member_id)
    if service_type:
        query = query.filter_by(service_type=service_type)
    if date_from:
        try:
            query = query.filter(Attendance.service_date >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Attendance.service_date <= date.fromisoformat(date_to))
        except ValueError:
            pass

    total = query.count()
    records = query.order_by(Attendance.service_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'records': [r.to_dict() for r in records.items],
        'total': total,
        'pages': records.pages,
        'current_page': page
    }), 200


@attendance_bp.route('/', methods=['POST'])
@jwt_required()
def mark_attendance():
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Support bulk marking
    if isinstance(data, list):
        created = []
        for item in data:
            record = _create_attendance_record(item, user_id)
            if record:
                db.session.add(record)
                created.append(record)
        db.session.commit()
        return jsonify([r.to_dict() for r in created]), 201

    # Single record
    required = ['member_id', 'service_type', 'service_date']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Check duplicate
    existing = Attendance.query.filter_by(
        member_id=data['member_id'],
        service_type=data['service_type'],
        service_date=date.fromisoformat(data['service_date'])
    ).first()
    if existing:
        return jsonify({'error': 'Attendance already recorded for this member and service'}), 409

    record = _create_attendance_record(data, user_id)
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


def _create_attendance_record(data, user_id):
    try:
        return Attendance(
            member_id=data['member_id'],
            service_type=data['service_type'],
            service_date=date.fromisoformat(data['service_date']),
            notes=data.get('notes'),
            recorded_by=int(user_id)
        )
    except Exception:
        return None


@attendance_bp.route('/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_attendance(record_id):
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'secretary']:
        return jsonify({'error': 'Insufficient permissions'}), 403
    record = Attendance.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({'message': 'Record deleted'}), 200


@attendance_bp.route('/service-types', methods=['GET'])
@jwt_required()
def get_service_types():
    return jsonify(SERVICE_TYPES), 200


@attendance_bp.route('/stats/summary', methods=['GET'])
@jwt_required()
def attendance_summary():
    # Last 12 weeks attendance per service
    from datetime import timedelta
    today = date.today()
    weeks_back = 12
    start_date = today - timedelta(weeks=weeks_back)

    records = db.session.query(
        Attendance.service_date,
        Attendance.service_type,
        func.count(Attendance.id).label('count')
    ).filter(
        Attendance.service_date >= start_date
    ).group_by(
        Attendance.service_date,
        Attendance.service_type
    ).order_by(Attendance.service_date).all()

    # Top attendees
    top = db.session.query(
        Member.first_name, Member.last_name, Member.member_id,
        func.count(Attendance.id).label('count')
    ).join(Attendance, Attendance.member_id == Member.id).group_by(
        Member.id
    ).order_by(func.count(Attendance.id).desc()).limit(10).all()

    # Total this month
    first_of_month = today.replace(day=1)
    this_month = Attendance.query.filter(
        Attendance.service_date >= first_of_month
    ).count()

    return jsonify({
        'weekly_trend': [
            {
                'date': str(r.service_date),
                'service_type': r.service_type,
                'count': r.count
            } for r in records
        ],
        'top_attendees': [
            {
                'name': f'{t[0]} {t[1]}',
                'member_id': t[2],
                'count': t[3]
            } for t in top
        ],
        'this_month_total': this_month,
        'total_records': Attendance.query.count()
    }), 200
