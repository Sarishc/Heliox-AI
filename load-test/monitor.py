"""
System monitoring during load test
Collects CPU, memory, DB, Redis metrics
"""
import psutil
import time
import json
import redis
from datetime import datetime
from pathlib import Path

# Configuration
MONITOR_INTERVAL = 5  # seconds
OUTPUT_DIR = Path(__file__).parent / "results"
OUTPUT_DIR.mkdir(exist_ok=True)

# Redis connection
REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "db": 0
}


class SystemMonitor:
    def __init__(self):
        self.metrics = []
        self.slow_queries = []
        self.redis_client = None
        
        try:
            self.redis_client = redis.Redis(**REDIS_CONFIG)
            self.redis_client.ping()
            print("✅ Connected to Redis")
        except Exception as e:
            print(f"⚠️  Redis connection failed: {e}")
    
    def get_docker_stats(self):
        """Get Docker container stats"""
        stats = {}
        
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t")
                        if len(parts) == 4:
                            name, cpu, mem_usage, mem_perc = parts
                            stats[name] = {
                                "cpu": cpu,
                                "memory_usage": mem_usage,
                                "memory_percent": mem_perc
                            }
        except Exception as e:
            print(f"⚠️  Docker stats failed: {e}")
        
        return stats
    
    def get_system_metrics(self):
        """Collect system-wide metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_mb": psutil.virtual_memory().available / (1024 * 1024),
            "disk_io": psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
        }
    
    def get_db_metrics(self):
        """Collect database metrics via Docker exec"""
        metrics = {}
        
        try:
            import subprocess
            
            # Active connections
            result = subprocess.run(
                ["docker", "exec", "heliox-postgres", "psql", "-U", "postgres", "-d", "heliox", "-t", "-c",
                 "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                metrics["active_connections"] = int(result.stdout.strip())
            
            # Total connections
            result = subprocess.run(
                ["docker", "exec", "heliox-postgres", "psql", "-U", "postgres", "-d", "heliox", "-t", "-c",
                 "SELECT count(*) FROM pg_stat_activity;"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                metrics["total_connections"] = int(result.stdout.strip())
            
            # Database size
            result = subprocess.run(
                ["docker", "exec", "heliox-postgres", "psql", "-U", "postgres", "-d", "heliox", "-t", "-c",
                 "SELECT pg_database_size('heliox') / (1024 * 1024);"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                metrics["database_size_mb"] = float(result.stdout.strip())
            
            # Lock count
            result = subprocess.run(
                ["docker", "exec", "heliox-postgres", "psql", "-U", "postgres", "-d", "heliox", "-t", "-c",
                 "SELECT count(*) FROM pg_locks;"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                metrics["lock_count"] = int(result.stdout.strip())
        
        except Exception as e:
            print(f"⚠️  DB metrics collection failed: {e}")
        
        return metrics
    
    def get_redis_metrics(self):
        """Collect Redis metrics"""
        if not self.redis_client:
            return {}
        
        try:
            info = self.redis_client.info()
            return {
                "used_memory_mb": info.get("used_memory", 0) / (1024 * 1024),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            print(f"⚠️  Redis metrics collection failed: {e}")
            return {}
    
    def collect(self):
        """Collect all metrics"""
        timestamp = datetime.utcnow().isoformat()
        
        metric = {
            "timestamp": timestamp,
            "system": self.get_system_metrics(),
            "docker": self.get_docker_stats(),
            "database": self.get_db_metrics(),
            "redis": self.get_redis_metrics()
        }
        
        self.metrics.append(metric)
        return metric
    
    def run(self, duration_seconds):
        """Run monitoring for specified duration"""
        print(f"\n🔍 Starting system monitoring for {duration_seconds} seconds...")
        print(f"📊 Collecting metrics every {MONITOR_INTERVAL} seconds\n")
        
        start_time = time.time()
        iteration = 0
        
        try:
            while time.time() - start_time < duration_seconds:
                iteration += 1
                metric = self.collect()
                
                # Print summary
                print(f"\n[{iteration}] {metric['timestamp']}")
                print(f"  CPU: {metric['system']['cpu_percent']:.1f}% | "
                      f"Memory: {metric['system']['memory_percent']:.1f}% | "
                      f"DB Connections: {metric['database'].get('active_connections', 'N/A')}/{metric['database'].get('total_connections', 'N/A')} | "
                      f"Redis Clients: {metric['redis'].get('connected_clients', 'N/A')}")
                
                if metric['database'].get('slow_query_count', 0) > 0:
                    print(f"  ⚠️  {metric['database']['slow_query_count']} slow queries detected!")
                
                # Check for high resource usage
                if metric['system']['cpu_percent'] > 80:
                    print(f"  🔥 HIGH CPU USAGE: {metric['system']['cpu_percent']:.1f}%")
                
                if metric['system']['memory_percent'] > 85:
                    print(f"  🔥 HIGH MEMORY USAGE: {metric['system']['memory_percent']:.1f}%")
                
                time.sleep(MONITOR_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring interrupted by user")
        
        finally:
            self.save_results()
    
    def save_results(self):
        """Save collected metrics to files"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Save metrics
        metrics_file = OUTPUT_DIR / f"metrics_{timestamp}.json"
        with open(metrics_file, "w") as f:
            json.dump(self.metrics, f, indent=2)
        print(f"\n✅ Metrics saved to {metrics_file}")
        
        # Save slow queries
        if self.slow_queries:
            slow_queries_file = OUTPUT_DIR / f"slow_queries_{timestamp}.json"
            with open(slow_queries_file, "w") as f:
                json.dump(self.slow_queries, f, indent=2)
            print(f"✅ Slow queries saved to {slow_queries_file}")
        
        # Generate summary
        self.generate_summary(timestamp)
    
    def generate_summary(self, timestamp):
        """Generate performance summary"""
        if not self.metrics:
            return
        
        summary_file = OUTPUT_DIR / f"summary_{timestamp}.txt"
        
        with open(summary_file, "w") as f:
            f.write("="*80 + "\n")
            f.write("HELIOX PERFORMANCE TEST SUMMARY\n")
            f.write("="*80 + "\n\n")
            
            # CPU stats
            cpu_values = [m['system']['cpu_percent'] for m in self.metrics]
            f.write(f"CPU Usage:\n")
            f.write(f"  Average: {sum(cpu_values)/len(cpu_values):.1f}%\n")
            f.write(f"  Peak: {max(cpu_values):.1f}%\n")
            f.write(f"  Min: {min(cpu_values):.1f}%\n\n")
            
            # Memory stats
            mem_values = [m['system']['memory_percent'] for m in self.metrics]
            f.write(f"Memory Usage:\n")
            f.write(f"  Average: {sum(mem_values)/len(mem_values):.1f}%\n")
            f.write(f"  Peak: {max(mem_values):.1f}%\n")
            f.write(f"  Min: {min(mem_values):.1f}%\n\n")
            
            # Database stats
            db_conn_values = [m['database'].get('active_connections', 0) for m in self.metrics]
            if db_conn_values:
                f.write(f"Database Connections:\n")
                f.write(f"  Average Active: {sum(db_conn_values)/len(db_conn_values):.1f}\n")
                f.write(f"  Peak Active: {max(db_conn_values)}\n\n")
            
            # Slow queries
            f.write(f"Slow Queries (>500ms): {len(self.slow_queries)}\n\n")
            
            if self.slow_queries:
                f.write("Top 5 Slowest Queries:\n")
                sorted_queries = sorted(self.slow_queries, key=lambda x: x['duration_seconds'], reverse=True)[:5]
                for i, sq in enumerate(sorted_queries, 1):
                    f.write(f"  {i}. Duration: {sq['duration_seconds']:.2f}s\n")
                    f.write(f"     Query: {sq['query'][:100]}...\n\n")
            
            # Redis stats
            redis_ops = [m['redis'].get('instantaneous_ops_per_sec', 0) for m in self.metrics if m['redis']]
            if redis_ops:
                f.write(f"Redis Operations/sec:\n")
                f.write(f"  Average: {sum(redis_ops)/len(redis_ops):.1f}\n")
                f.write(f"  Peak: {max(redis_ops):.1f}\n\n")
            
            f.write("="*80 + "\n")
        
        print(f"✅ Summary saved to {summary_file}")
        
        # Close connections
        if self.redis_client:
            self.redis_client.close()


if __name__ == "__main__":
    import sys
    
    duration = 300  # Default 5 minutes
    if len(sys.argv) > 1:
        duration = int(sys.argv[1])
    
    monitor = SystemMonitor()
    monitor.run(duration)
