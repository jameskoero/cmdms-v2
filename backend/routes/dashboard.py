from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from models import db, Member, Attendance, Finance, Event, User
from datetime import date, datetime, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    today = date.today()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)

    # Member stats
    total_members = Member.query.filter_by(membership_status='active').count()
    new_this_month = Member.query.filter(
        Member.date_joined >= first_of_month,
        Member.membership_status == 'active'
    ).count()

    # Attendance - last Sunday
    last_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    last_service = Attendance.query.filter(
        Attendance.service_date == last_sunday,
        Attendance.service_type == 'Sunday Morning'
    ).count()

    # Finance
    income_types = ['tithe', 'offering', 'donation', 'project_fund', 'other']
    monthly_income = db.session.query(func.sum(Finance.amount)).filter(
        Finance.transaction_type.in_(income_types),
        Finance.transaction_date >= first_of_month
    ).scalar() or 0

    monthly_expense = db.session.query(func.sum(Finance.amount)).filter(
        Finance.transaction_type == 'expense',
        Finance.transaction_date >= first_of_month
    ).scalar() or 0

    annual_income = db.session.query(func.sum(Finance.amount)).filter(
        Finance.transaction_type.in_(income_types),
        Finance.transaction_date >= first_of_year
    ).scalar() or 0

    # Upcoming events
    upcoming_events = Event.query.filter(
        Event.start_date >= datetime.utcnow(),
        Event.status != 'cancelled'
    ).order_by(Event.start_date).limit(5).all()

    # Attendance trend (last 8 Sundays)
    trend_data = db.session.query(
        Attendance.service_date,
        func.count(Attendance.id).label('count')
    ).filter(
        Attendance.service_type == 'Sunday Morning',
        Attendance.service_date >= today - timedelta(weeks=8)
    ).group_by(Attendance.service_date).order_by(Attendance.service_date).all()

    # Monthly finance chart (last 6 months)
    six_months_ago = today - timedelta(days=180)
    monthly_finance = db.session.query(
        func.extract('year', Finance.transaction_date).label('year'),
        func.extract('month', Finance.transaction_date).label('month'),
        Finance.transaction_type,
        func.sum(Finance.amount).label('total')
    ).filter(
        Finance.transaction_date >= six_months_ago
    ).group_by('year', 'month', Finance.transaction_type).all()

    return jsonify({
        'members': {
            'total': total_members,
            'new_this_month': new_this_month,
            'male': Member.query.filter_by(gender='Male', membership_status='active').count(),
            'female': Member.query.filter_by(gender='Female', membership_status='active').count()
        },
        'attendance': {
            'last_service': last_service,
            'this_month': Attendance.query.filter(
                Attendance.service_date >= first_of_month
            ).count()
        },
        'finance': {
            'monthly_income': float(monthly_income),
            'monthly_expense': float(monthly_expense),
            'monthly_net': float(monthly_income) - float(monthly_expense),
            'annual_income': float(annual_income)
        },
        'upcoming_events': [e.to_dict() for e in upcoming_events],
        'attendance_trend': [
            {'date': str(r.service_date), 'count': r.count}
            for r in trend_data
        ],
        'finance_trend': [
            {
                'year': int(r.year),
                'month': int(r.month),
                'type': r.transaction_type,
                'total': float(r.total)
            } for r in monthly_finance
        ],
        'total_users': User.query.filter_by(is_active=True).count()
    }), 200
