"""
Fake API Service for Performance Testing
A simple Flask API that simulates various endpoints with configurable delays and responses
"""

import json
import time
import secrets
import os
from datetime import datetime
from flask import Flask, request, jsonify
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory storage for demo purposes
users = {}
orders = {}
payments = {}

# Configuration
RESPONSE_DELAY_MIN = float(os.environ.get('RESPONSE_DELAY_MIN', '0.1'))
RESPONSE_DELAY_MAX = float(os.environ.get('RESPONSE_DELAY_MAX', '0.5'))
ERROR_RATE = float(os.environ.get('ERROR_RATE', '0.05'))  # 5% error rate
MEMORY_LEAK_SIMULATION = os.environ.get('MEMORY_LEAK_SIMULATION', 'false').lower() == 'true'

# Memory leak simulation
memory_hog = []

# Initialize secure random generator for delay simulation
secure_random = secrets.SystemRandom()

def simulate_processing_time():
    """Simulate realistic API processing time"""
    delay = secure_random.uniform(RESPONSE_DELAY_MIN, RESPONSE_DELAY_MAX)
    time.sleep(delay)

def should_return_error():
    """Randomly return errors based on configured error rate"""
    return secure_random.random() < ERROR_RATE

def simulate_memory_leak():
    """Simulate memory leak for endurance testing"""
    if MEMORY_LEAK_SIMULATION:
        # Add some data to memory that won't be cleaned up
        memory_hog.append('x' * 1024)  # Add 1KB each time

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint - always returns healthy for ECS health checks"""
    # Don't simulate processing time or errors for health checks
    # This ensures ECS service stays healthy
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'memory_usage': len(memory_hog) if MEMORY_LEAK_SIMULATION else 0
    })

@app.route('/auth/login', methods=['POST'])
@app.route('/api/v1/users/login', methods=['POST'])
def login():
    """User authentication endpoint"""
    simulate_processing_time()
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Authentication service unavailable'}), 503
    
    data = request.get_json() or {}
    username = data.get('username', 'testuser')
    password = data.get('password', 'password')
    
    # Simulate authentication logic
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    # Generate fake JWT token
    token = f"fake-jwt-token-{username}-{int(time.time())}"
    
    # Store user session
    users[token] = {
        'username': username,
        'login_time': datetime.utcnow().isoformat(),
        'session_id': f"session-{secure_random.randint(1000, 9999)}"
    }
    
    return jsonify({
        'token': token,
        'username': username,
        'expires_in': 3600,
        'session_id': users[token]['session_id']
    })

@app.route('/auth/logout', methods=['POST'])
def logout():
    """User logout endpoint"""
    simulate_processing_time()
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token in users:
        del users[token]
        return jsonify({'message': 'Logged out successfully'})
    
    return jsonify({'error': 'Invalid token'}), 401

@app.route('/orders', methods=['GET', 'POST'])
@app.route('/api/v1/orders', methods=['GET', 'POST'])
@app.route('/api/v1/cart/items', methods=['GET', 'POST'])
def handle_orders():
    """Orders endpoint - GET to list, POST to create"""
    simulate_processing_time()
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Orders service temporarily unavailable'}), 503
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    if request.method == 'GET':
        # List orders for user
        user_orders = [order for order in orders.values() if order.get('user_token') == token]
        return jsonify({
            'orders': user_orders,
            'total': len(user_orders),
            'timestamp': datetime.utcnow().isoformat()
        })
    
    elif request.method == 'POST':
        # Create new order
        data = request.get_json() or {}
        
        order_id = f"order-{secure_random.randint(10000, 99999)}"
        order = {
            'order_id': order_id,
            'user_token': token,
            'username': users[token]['username'],
            'items': data.get('items', []),
            'total_amount': data.get('total_amount', secure_random.uniform(10.0, 500.0)),
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
        
        orders[order_id] = order
        
        return jsonify(order), 201

@app.route('/orders/<order_id>', methods=['GET', 'PUT', 'DELETE'])
@app.route('/api/v1/orders/<order_id>', methods=['GET', 'PUT', 'DELETE'])
@app.route('/api/v1/products/<order_id>', methods=['GET'])
@app.route('/api/v1/products/search', methods=['GET'])
def handle_single_order(order_id):
    """Handle individual order operations"""
    simulate_processing_time()
    
    if should_return_error():
        return jsonify({'error': 'Order service error'}), 500
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    if order_id not in orders:
        return jsonify({'error': 'Order not found'}), 404
    
    order = orders[order_id]
    
    # Check if user owns this order
    if order.get('user_token') != token:
        return jsonify({'error': 'Access denied'}), 403
    
    if request.method == 'GET':
        return jsonify(order)
    
    elif request.method == 'PUT':
        # Update order
        data = request.get_json() or {}
        order.update(data)
        order['updated_at'] = datetime.utcnow().isoformat()
        return jsonify(order)
    
    elif request.method == 'DELETE':
        # Cancel order
        del orders[order_id]
        return jsonify({'message': 'Order cancelled successfully'})

@app.route('/payment/process', methods=['POST'])
@app.route('/api/v1/payments', methods=['POST'])
def process_payment():
    """Payment processing endpoint"""
    # Simulate longer processing time for payments
    time.sleep(secure_random.uniform(0.5, 2.0))
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Payment gateway timeout'}), 504
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json() or {}
    order_id = data.get('order_id')
    payment_method = data.get('payment_method', 'credit_card')
    amount = data.get('amount', 0)
    
    if not order_id or not amount:
        return jsonify({'error': 'Order ID and amount required'}), 400
    
    # Simulate payment processing
    payment_id = f"payment-{secure_random.randint(100000, 999999)}"
    
    # Random payment failure (in addition to general error rate)
    if secure_random.random() < 0.02:  # 2% payment-specific failure rate
        return jsonify({
            'payment_id': payment_id,
            'status': 'failed',
            'error': 'Payment declined by bank',
            'order_id': order_id
        }), 402
    
    payment = {
        'payment_id': payment_id,
        'order_id': order_id,
        'user_token': token,
        'amount': amount,
        'payment_method': payment_method,
        'status': 'completed',
        'transaction_id': f"txn-{secure_random.randint(1000000, 9999999)}",
        'processed_at': datetime.utcnow().isoformat()
    }
    
    payments[payment_id] = payment
    
    # Update order status if it exists
    if order_id in orders:
        orders[order_id]['status'] = 'paid'
        orders[order_id]['payment_id'] = payment_id
    
    return jsonify(payment)

@app.route('/api/v1/cart', methods=['GET'])
def get_cart():
    """Get cart contents - alias for orders"""
    return handle_orders()

@app.route('/api/v1/users', methods=['GET', 'POST'])
def handle_users():
    """User management endpoint"""
    simulate_processing_time()
    
    if should_return_error():
        return jsonify({'error': 'User service unavailable'}), 503
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if request.method == 'GET':
        # List users (admin only simulation)
        if token not in users:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Simulate user list
        user_list = []
        for i in range(1, 21):  # 20 demo users
            user_list.append({
                'id': i,
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'created_at': datetime.utcnow().isoformat(),
                'status': 'active' if i % 10 != 0 else 'inactive'
            })
        
        return jsonify({
            'users': user_list,
            'total': len(user_list),
            'page': 1,
            'per_page': 20
        })
    
    elif request.method == 'POST':
        # Create new user
        data = request.get_json() or {}
        
        user_id = secure_random.randint(100, 999)
        new_user = {
            'id': user_id,
            'username': data.get('username', f'user{user_id}'),
            'email': data.get('email', f'user{user_id}@example.com'),
            'created_at': datetime.utcnow().isoformat(),
            'status': 'active'
        }
        
        return jsonify(new_user), 201

@app.route('/api/v1/users/<user_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_user(user_id):
    """Handle individual user operations"""
    simulate_processing_time()
    
    if should_return_error():
        return jsonify({'error': 'User service error'}), 500
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Simulate user data
    user_data = {
        'id': int(user_id),
        'username': f'user{user_id}',
        'email': f'user{user_id}@example.com',
        'created_at': datetime.utcnow().isoformat(),
        'status': 'active',
        'profile': {
            'first_name': f'User',
            'last_name': f'{user_id}',
            'phone': f'+1-555-{user_id:04d}',
            'address': {
                'street': f'{user_id} Demo Street',
                'city': 'Demo City',
                'state': 'DC',
                'zip': f'{user_id:05d}'
            }
        }
    }
    
    if request.method == 'GET':
        return jsonify(user_data)
    
    elif request.method == 'PUT':
        # Update user
        data = request.get_json() or {}
        user_data.update(data)
        user_data['updated_at'] = datetime.utcnow().isoformat()
        return jsonify(user_data)
    
    elif request.method == 'DELETE':
        # Delete user
        return jsonify({'message': f'User {user_id} deleted successfully'})

@app.route('/api/v1/inventory', methods=['GET'])
@app.route('/api/v1/products', methods=['GET'])
def get_inventory():
    """Get product inventory"""
    simulate_processing_time()
    
    if should_return_error():
        return jsonify({'error': 'Inventory service unavailable'}), 503
    
    # Generate demo products
    products = []
    categories = ['Electronics', 'Clothing', 'Books', 'Home & Garden', 'Sports']
    
    for i in range(1, 51):  # 50 demo products
        products.append({
            'id': i,
            'name': f'Demo Product {i}',
            'description': f'This is a demo product for testing purposes - Product {i}',
            'price': round(secure_random.uniform(9.99, 999.99), 2),
            'category': secure_random.choice(categories),
            'stock': secure_random.randint(0, 100),
            'sku': f'DEMO-{i:04d}',
            'created_at': datetime.utcnow().isoformat(),
            'status': 'active' if i % 20 != 0 else 'discontinued'
        })
    
    # Apply filters
    category = request.args.get('category')
    if category:
        products = [p for p in products if p['category'].lower() == category.lower()]
    
    min_price = request.args.get('min_price')
    if min_price:
        products = [p for p in products if p['price'] >= float(min_price)]
    
    max_price = request.args.get('max_price')
    if max_price:
        products = [p for p in products if p['price'] <= float(max_price)]
    
    return jsonify({
        'products': products,
        'total': len(products),
        'categories': categories,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/v1/analytics/dashboard', methods=['GET'])
def analytics_dashboard():
    """Analytics dashboard endpoint with heavy data processing simulation"""
    # Simulate longer processing for analytics
    time.sleep(secure_random.uniform(1.0, 3.0))
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Analytics service timeout'}), 504
    
    # Generate realistic analytics data
    analytics_data = {
        'summary': {
            'total_users': secure_random.randint(1000, 10000),
            'active_users_today': secure_random.randint(100, 1000),
            'total_orders': secure_random.randint(500, 5000),
            'revenue_today': round(secure_random.uniform(1000, 50000), 2),
            'conversion_rate': round(secure_random.uniform(2.5, 8.5), 2)
        },
        'hourly_traffic': [
            {
                'hour': i,
                'requests': secure_random.randint(50, 500),
                'unique_users': secure_random.randint(20, 200),
                'errors': secure_random.randint(0, 10)
            } for i in range(24)
        ],
        'top_products': [
            {
                'id': i,
                'name': f'Popular Product {i}',
                'sales': secure_random.randint(10, 100),
                'revenue': round(secure_random.uniform(100, 5000), 2)
            } for i in range(1, 11)
        ],
        'geographic_data': [
            {'country': 'US', 'users': secure_random.randint(100, 1000)},
            {'country': 'CA', 'users': secure_random.randint(50, 500)},
            {'country': 'UK', 'users': secure_random.randint(30, 300)},
            {'country': 'DE', 'users': secure_random.randint(20, 200)},
            {'country': 'FR', 'users': secure_random.randint(15, 150)}
        ],
        'generated_at': datetime.utcnow().isoformat(),
        'processing_time_ms': secure_random.randint(1000, 3000)
    }
    
    return jsonify(analytics_data)

@app.route('/api/v1/notifications', methods=['GET', 'POST'])
def handle_notifications():
    """Notification system endpoint"""
    simulate_processing_time()
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    if request.method == 'GET':
        # Get user notifications
        notifications = []
        for i in range(1, 11):  # 10 demo notifications
            notifications.append({
                'id': i,
                'title': f'Notification {i}',
                'message': f'This is demo notification {i} for testing purposes',
                'type': secure_random.choice(['info', 'warning', 'success', 'error']),
                'read': secure_random.choice([True, False]),
                'created_at': datetime.utcnow().isoformat()
            })
        
        return jsonify({
            'notifications': notifications,
            'unread_count': len([n for n in notifications if not n['read']]),
            'total': len(notifications)
        })
    
    elif request.method == 'POST':
        # Send notification
        data = request.get_json() or {}
        
        notification = {
            'id': secure_random.randint(1000, 9999),
            'title': data.get('title', 'Demo Notification'),
            'message': data.get('message', 'Demo notification message'),
            'type': data.get('type', 'info'),
            'read': False,
            'created_at': datetime.utcnow().isoformat(),
            'sent_to': users[token]['username']
        }
        
        return jsonify(notification), 201

@app.route('/api/v1/search', methods=['GET'])
def search_endpoint():
    """Search endpoint with configurable response time"""
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    # Simulate search processing time based on query complexity
    search_delay = len(query) * 0.1 + secure_random.uniform(0.2, 1.0)
    time.sleep(min(search_delay, 3.0))  # Cap at 3 seconds
    
    if should_return_error():
        return jsonify({'error': 'Search service unavailable'}), 503
    
    # Generate search results
    results = []
    if query:
        for i in range(1, min(21, len(query) * 3)):  # Results based on query length
            results.append({
                'id': i,
                'title': f'Search Result {i} for "{query}"',
                'description': f'This is a demo search result matching "{query}"',
                'category': category or secure_random.choice(['Electronics', 'Books', 'Clothing']),
                'relevance_score': round(secure_random.uniform(0.5, 1.0), 2),
                'url': f'/products/{i}'
            })
    
    return jsonify({
        'query': query,
        'results': results,
        'total_results': len(results),
        'search_time_ms': int(search_delay * 1000),
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/payment/<payment_id>', methods=['GET'])
def get_payment(payment_id):
    """Get payment details"""
    simulate_processing_time()
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    if payment_id not in payments:
        return jsonify({'error': 'Payment not found'}), 404
    
    payment = payments[payment_id]
    
    if payment.get('user_token') != token:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(payment)

@app.route('/data/heavy', methods=['GET'])
def heavy_data_endpoint():
    """Endpoint that returns large amounts of data for testing"""
    simulate_processing_time()
    
    # Generate large response
    size = int(request.args.get('size', '1000'))  # Number of records
    
    data = []
    for i in range(size):
        data.append({
            'id': i,
            'name': f'Record {i}',
            'description': f'This is a description for record {i}' * 10,  # Make it longer
            'timestamp': datetime.utcnow().isoformat(),
            'random_data': ''.join(secure_random.choices('abcdefghijklmnopqrstuvwxyz', k=100))
        })
    
    return jsonify({
        'records': data,
        'total': len(data),
        'generated_at': datetime.utcnow().isoformat()
    })

@app.route('/cpu/intensive', methods=['GET'])
def cpu_intensive_endpoint():
    """CPU intensive endpoint for stress testing"""
    # Simulate CPU intensive work
    iterations = int(request.args.get('iterations', '100000'))
    
    start_time = time.time()
    result = 0
    for i in range(iterations):
        result += i ** 2
    
    processing_time = time.time() - start_time
    
    return jsonify({
        'result': result,
        'iterations': iterations,
        'processing_time_seconds': processing_time,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/v1/files/upload', methods=['POST'])
def upload_file():
    """File upload simulation endpoint"""
    # Simulate file processing time
    time.sleep(secure_random.uniform(2.0, 5.0))
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'File upload service unavailable'}), 503
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Simulate file upload processing
    file_id = f"file-{secure_random.randint(100000, 999999)}"
    file_size = secure_random.randint(1024, 10485760)  # 1KB to 10MB
    
    upload_result = {
        'file_id': file_id,
        'filename': f'demo-file-{file_id}.pdf',
        'size_bytes': file_size,
        'content_type': 'application/pdf',
        'upload_time': datetime.utcnow().isoformat(),
        'status': 'uploaded',
        'url': f'/api/v1/files/{file_id}',
        'user': users[token]['username']
    }
    
    return jsonify(upload_result), 201

@app.route('/api/v1/files/<file_id>', methods=['GET', 'DELETE'])
def handle_file(file_id):
    """File download/delete endpoint"""
    simulate_processing_time()
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    if request.method == 'GET':
        # Simulate file download
        file_info = {
            'file_id': file_id,
            'filename': f'demo-file-{file_id}.pdf',
            'size_bytes': secure_random.randint(1024, 10485760),
            'content_type': 'application/pdf',
            'created_at': datetime.utcnow().isoformat(),
            'download_url': f'https://demo-cdn.example.com/files/{file_id}',
            'expires_at': datetime.utcnow().isoformat()
        }
        return jsonify(file_info)
    
    elif request.method == 'DELETE':
        # Delete file
        return jsonify({'message': f'File {file_id} deleted successfully'})

@app.route('/api/v1/reports/generate', methods=['POST'])
def generate_report():
    """Report generation endpoint - CPU intensive"""
    # Simulate heavy report generation
    iterations = int(request.args.get('complexity', '500000'))
    
    start_time = time.time()
    result = 0
    for i in range(iterations):
        result += i ** 2
        if i % 50000 == 0:
            time.sleep(0.01)  # Simulate I/O operations
    
    processing_time = time.time() - start_time
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Report generation failed'}), 500
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    report_id = f"report-{secure_random.randint(100000, 999999)}"
    
    report_data = {
        'report_id': report_id,
        'type': 'performance_analysis',
        'status': 'completed',
        'generated_by': users[token]['username'],
        'processing_time_seconds': round(processing_time, 2),
        'complexity_level': iterations,
        'data_points': secure_random.randint(1000, 10000),
        'file_size_mb': round(secure_random.uniform(1.0, 50.0), 2),
        'download_url': f'/api/v1/reports/{report_id}/download',
        'created_at': datetime.utcnow().isoformat(),
        'expires_at': datetime.utcnow().isoformat()
    }
    
    return jsonify(report_data), 201

@app.route('/api/v1/cache/clear', methods=['POST'])
def clear_cache():
    """Cache clearing endpoint"""
    simulate_processing_time()
    
    if should_return_error():
        return jsonify({'error': 'Cache service unavailable'}), 503
    
    # Simulate cache clearing
    cache_stats = {
        'cache_cleared': True,
        'items_removed': secure_random.randint(100, 10000),
        'memory_freed_mb': round(secure_random.uniform(10.0, 500.0), 2),
        'operation_time_ms': secure_random.randint(100, 2000),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    return jsonify(cache_stats)

@app.route('/api/v1/batch/process', methods=['POST'])
def batch_process():
    """Batch processing endpoint"""
    data = request.get_json() or {}
    batch_size = data.get('batch_size', 100)
    
    # Simulate batch processing time based on size
    processing_time = batch_size * 0.01 + secure_random.uniform(0.5, 2.0)
    time.sleep(min(processing_time, 10.0))  # Cap at 10 seconds
    
    simulate_memory_leak()
    
    if should_return_error():
        return jsonify({'error': 'Batch processing failed'}), 500
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token not in users:
        return jsonify({'error': 'Authentication required'}), 401
    
    batch_id = f"batch-{secure_random.randint(100000, 999999)}"
    
    # Simulate some failures in batch
    success_count = int(batch_size * secure_random.uniform(0.85, 0.98))
    failed_count = batch_size - success_count
    
    batch_result = {
        'batch_id': batch_id,
        'total_items': batch_size,
        'successful': success_count,
        'failed': failed_count,
        'success_rate': round((success_count / batch_size) * 100, 2),
        'processing_time_seconds': round(processing_time, 2),
        'started_by': users[token]['username'],
        'started_at': datetime.utcnow().isoformat(),
        'completed_at': datetime.utcnow().isoformat(),
        'status': 'completed'
    }
    
    return jsonify(batch_result), 201

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get API statistics"""
    return jsonify({
        'active_users': len(users),
        'total_orders': len(orders),
        'total_payments': len(payments),
        'memory_usage_kb': len(memory_hog) if MEMORY_LEAK_SIMULATION else 0,
        'configuration': {
            'response_delay_min': RESPONSE_DELAY_MIN,
            'response_delay_max': RESPONSE_DELAY_MAX,
            'error_rate': ERROR_RATE,
            'memory_leak_simulation': MEMORY_LEAK_SIMULATION
        },
        'endpoints': {
            'authentication': ['/auth/login', '/auth/logout'],
            'users': ['/api/v1/users', '/api/v1/users/{id}'],
            'orders': ['/api/v1/orders', '/api/v1/orders/{id}'],
            'payments': ['/api/v1/payments', '/payment/process'],
            'products': ['/api/v1/products', '/api/v1/inventory'],
            'analytics': ['/api/v1/analytics/dashboard'],
            'search': ['/api/v1/search'],
            'files': ['/api/v1/files/upload', '/api/v1/files/{id}'],
            'reports': ['/api/v1/reports/generate'],
            'utilities': ['/api/v1/cache/clear', '/api/v1/batch/process'],
            'testing': ['/data/heavy', '/cpu/intensive', '/health']
        },
        'timestamp': datetime.utcnow().isoformat()
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    # Allow host binding to be configured - defaults to 0.0.0.0 for containerized deployment
    host = os.environ.get('HOST', '0.0.0.0')
    
    logger.info(f"Starting Fake API Service on {host}:{port}")
    logger.info(f"Configuration: delay={RESPONSE_DELAY_MIN}-{RESPONSE_DELAY_MAX}s, error_rate={ERROR_RATE}")
    
    app.run(host=host, port=port, debug=debug)