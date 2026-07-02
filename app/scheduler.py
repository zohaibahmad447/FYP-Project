"""
Background Task Scheduler for Quick Care
Schedules and runs periodic background jobs
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import atexit

# Global scheduler instance
scheduler = None

def init_scheduler(app):
    """Initialize and start the background scheduler"""
    global scheduler
    
    if scheduler is not None:
        return  # Already initialized
    
    scheduler = BackgroundScheduler(daemon=True)
    
    # Job Wrappers to provide Flask application context
    def run_payment_cleanup():
        with app.app_context():
            from app.utils.cleanup_expired_payments import cleanup_expired_payments
            cleanup_expired_payments()
            
    def run_completion_reviews():
        with app.app_context():
            from app.utils.process_completion_reviews import process_completion_reviews
            process_completion_reviews()
            
    def run_expired_appointments_check():
        with app.app_context():
            from app.jobs.check_expired_appointments import check_expired_appointments
            check_expired_appointments()
    
    # Add job: Run payment cleanup every 10 minutes
    scheduler.add_job(
        func=run_payment_cleanup,
        trigger=IntervalTrigger(minutes=10),
        next_run_time=datetime.now(),
        id='cleanup_expired_payments',
        name='Cancel appointments with expired payment deadlines',
        replace_existing=True
    )
    
    # Add job: Run completion review auto-complete every hour
    scheduler.add_job(
        func=run_completion_reviews,
        trigger=IntervalTrigger(hours=1),
        next_run_time=datetime.now(),
        id='process_completion_reviews',
        name='Auto-complete appointments after 24-hour review period',
        replace_existing=True
    )
    
    # Add job: Check for expired appointments and handle no-shows every 5 minutes
    scheduler.add_job(
        func=run_expired_appointments_check,
        trigger=IntervalTrigger(minutes=5),
        next_run_time=datetime.now(),
        id='check_expired_appointments',
        name='Detect expired appointments and handle no-show scenarios',
        replace_existing=True
    )
    
    # Start the scheduler
    scheduler.start()
    
    # Log startup (single line to keep terminal clean)
    with app.app_context():
        from app.utils.timezone import get_pakistan_now
        print(f"[{get_pakistan_now().strftime('%H:%M:%S')}] Scheduler started (payment 10m, completion 1h, expiry 5m)")
    
    # Shut down scheduler when app exits
    atexit.register(lambda: scheduler.shutdown() if scheduler else None)

def run_cleanup_now():
    """Manually trigger cleanup job (useful for testing)"""
    from app.utils.cleanup_expired_payments import cleanup_expired_payments
    cleanup_expired_payments()
