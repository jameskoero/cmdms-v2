from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Finance, TRANSACTION_TYPES, FINANCE_CATEGORIES
from datetime import date
from sqlalchemy import func

finance_bp = Blueprint('finance', __name__)


def require_finance_role(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') not in ['admin', 'treasurer']:
            return jsonify({'error': 'Finance access requires admin or treasurer role'}), 403
        return f(*args, **kwargs)
    return decorated


@finance_bp.route('/', methods=['GET'])
@jwt_required()
def get_transactions():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    tx_type = request.args.get('type', '')
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '').strip()

    query = Finance.query

    if tx_type:
        query = query.filter_by(transaction_type=tx_type)
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(
            Finance.reference.ilike(f'%{search}%') |
            Finance.description.ilike(f'%{search}%') |
            Finance.mpesa_ref.ilike(f'%{search}%')
        )
    if date_from:
        try:
            query = query.filter(Finance.transaction_date >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Finance.transaction_date <= date.fromisoformat(date_to))
        except ValueError:
            pass

    total = query.count()
    records = query.order_by(Finance.transaction_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'transactions': [r.to_dict() for r in records.items],
        'total': total,
        'pages': records.pages,
        'current_page': page
    }), 200


@finance_bp.route('/', methods=['POST'])
@jwt_required()
@require_finance_role
def create_transaction():
    user_id = get_jwt_identity()
    data = request.get_json()

    required = ['transaction_type', 'amount', 'transaction_date']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a positive number'}), 400

    transaction = Finance(
        reference=Finance.generate_reference(),
        transaction_type=data['transaction_type'],
        category=data.get('category'),
        amount=amount,
        currency='KES',
        description=data.get('description'),
        member_id=data.get('member_id'),
        payment_method=data.get('payment_method', 'cash'),
        mpesa_ref=data.get('mpesa_ref'),
        transaction_date=date.fromisoformat(data['transaction_date']),
        recorded_by=int(user_id),
        verified=data.get('verified', False),
        notes=data.get('notes')
    )

    db.session.add(transaction)
    db.session.commit()
    return jsonify(transaction.to_dict()), 201


@finance_bp.route('/<int:tx_id>', methods=['PUT'])
@jwt_required()
@require_finance_role
def update_transaction(tx_id):
    tx = Finance.query.get_or_404(tx_id)
    data = request.get_json()

    fields = ['transaction_type', 'category', 'description', 'payment_method',
              'mpesa_ref', 'verified', 'notes']
    for field in fields:
        if field in data:
            setattr(tx, field, data[field])

    if 'amount' in data:
        try:
            tx.amount = float(data['amount'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount'}), 400

    if 'transaction_date' in data:
        try:
            tx.transaction_date = date.fromisoformat(data['transaction_date'])
        except ValueError:
            pass

    db.session.commit()
    return jsonify(tx.to_dict()), 200


@finance_bp.route('/<int:tx_id>', methods=['DELETE'])
@jwt_required()
@require_finance_role
def delete_transaction(tx_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Only admin can delete transactions'}), 403
    tx = Finance.query.get_or_404(tx_id)
    db.session.delete(tx)
    db.session.commit()
    return jsonify({'message': 'Transaction deleted'}), 200


@finance_bp.route('/summary', methods=['GET'])
@jwt_required()
def finance_summary():
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', type=int)

    query = Finance.query.filter(
        func.extract('year', Finance.transaction_date) == year
    )
    if month:
        query = query.filter(func.extract('month', Finance.transaction_date) == month)

    # Income (not expense)
    income_types = ['tithe', 'offering', 'donation', 'project_fund', 'other']
    total_income = db.session.query(
        func.sum(Finance.amount)
    ).filter(
        Finance.transaction_type.in_(income_types),
        func.extract('year', Finance.transaction_date) == year
    )
    if month:
        total_income = total_income.filter(
            func.extract('month', Finance.transaction_date) == month
        )
    total_income = total_income.scalar() or 0

    total_expense = db.session.query(
        func.sum(Finance.amount)
    ).filter(
        Finance.transaction_type == 'expense',
        func.extract('year', Finance.transaction_date) == year
    )
    if month:
        total_expense = total_expense.filter(
            func.extract('month', Finance.transaction_date) == month
        )
    total_expense = total_expense.scalar() or 0

    # Monthly breakdown for charts
    monthly = db.session.query(
        func.extract('month', Finance.transaction_date).label('month'),
        Finance.transaction_type,
        func.sum(Finance.amount).label('total')
    ).filter(
        func.extract('year', Finance.transaction_date) == year
    ).group_by('month', Finance.transaction_type).all()

    # Category breakdown
    by_category = db.session.query(
        Finance.category,
        func.sum(Finance.amount).label('total')
    ).filter(
        func.extract('year', Finance.transaction_date) == year
    ).group_by(Finance.category).all()

    return jsonify({
        'total_income': float(total_income),
        'total_expense': float(total_expense),
        'net': float(total_income) - float(total_expense),
        'year': year,
        'monthly_breakdown': [
            {
                'month': int(r.month),
                'transaction_type': r.transaction_type,
                'total': float(r.total)
            } for r in monthly
        ],
        'by_category': [
            {'category': r.category or 'Uncategorized', 'total': float(r.total)}
            for r in by_category
        ]
    }), 200


@finance_bp.route('/transaction-types', methods=['GET'])
@jwt_required()
def get_transaction_types():
    return jsonify(TRANSACTION_TYPES), 200


@finance_bp.route('/categories', methods=['GET'])
@jwt_required()
def get_categories():
    return jsonify(FINANCE_CATEGORIES), 200
