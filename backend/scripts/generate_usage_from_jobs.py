"""Generate UsageSnapshot data from Job data for MVP."""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cost import UsageSnapshot
from app.models.job import Job

settings = get_settings()


def generate_usage_snapshots(db: Session, start_date: date, end_date: date):
    """
    Generate UsageSnapshot records by aggregating Job runtime hours per day.
    
    For each day and (provider, gpu_type) combination:
    1. Find all jobs that ran on that day
    2. Calculate total GPU hours used
    3. Create/update UsageSnapshot record
    
    Args:
        db: Database session
        start_date: Start date for generation
        end_date: End date for generation
    """
    print(f"Generating usage snapshots from {start_date} to {end_date}")
    
    current_date = start_date
    total_created = 0
    
    while current_date <= end_date:
        # Get all jobs that were running on this date
        stmt = (
            select(
                Job.provider,
                Job.gpu_type,
                func.sum(
                    func.extract(
                        'epoch',
                        func.least(Job.end_time, current_date + timedelta(days=1)) -
                        func.greatest(Job.start_time, current_date)
                    ) / 3600
                ).label('total_hours')
            )
            .where(
                Job.start_time.isnot(None),
                Job.end_time.isnot(None),
                func.date(Job.start_time) <= current_date,
                func.date(Job.end_time) >= current_date
            )
            .group_by(Job.provider, Job.gpu_type)
        )
        
        results = db.execute(stmt).all()
        
        for provider, gpu_type, total_hours in results:
            if total_hours and total_hours > 0:
                # Check if usage snapshot already exists
                existing = db.execute(
                    select(UsageSnapshot).where(
                        UsageSnapshot.date == current_date,
                        UsageSnapshot.provider == provider.lower(),
                        UsageSnapshot.gpu_type == gpu_type.lower()
                    )
                ).scalar_one_or_none()
                
                if existing:
                    # Update existing
                    existing.gpu_hours = Decimal(str(round(total_hours, 2)))
                    print(f"  Updated: {current_date} {provider} {gpu_type}: {total_hours:.2f} hours")
                else:
                    # Create new
                    usage = UsageSnapshot(
                        date=current_date,
                        provider=provider.lower(),
                        gpu_type=gpu_type.lower(),
                        gpu_hours=Decimal(str(round(total_hours, 2)))
                    )
                    db.add(usage)
                    total_created += 1
                    print(f"  Created: {current_date} {provider} {gpu_type}: {total_hours:.2f} hours")
        
        current_date += timedelta(days=1)
    
    db.commit()
    print(f"\nTotal usage snapshots created: {total_created}")
    
    # Show summary
    total_usage = db.execute(
        select(func.count(UsageSnapshot.id))
    ).scalar_one()
    print(f"Total usage snapshots in database: {total_usage}")


def main():
    """Main execution."""
    engine = create_engine(settings.DATABASE_URL)
    
    with Session(engine) as db:
        # Generate for the same period as our cost data
        start_date = date(2026, 1, 1)
        end_date = date(2026, 1, 14)
        
        generate_usage_snapshots(db, start_date, end_date)
        
        print("\n✅ Usage generation complete!")
        print("\nNow run:")
        print('  curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14"')


if __name__ == "__main__":
    main()

