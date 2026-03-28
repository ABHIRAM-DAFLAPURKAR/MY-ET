import subprocess
import pandas as pd
import matplotlib.pyplot as plt

def get_docker_stats():
    # Run the docker stats command once
    cmd = ['docker', 'stats', '--no-stream', '--format', '{{.Name}},{{.CPUPerc}},{{.MemUsage}}']
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
        return result.stdout.strip().split('\n')
    except Exception as e:
        print(f"Error fetching docker stats: {e}")
        return []

def generate_system_metrics():
    print("Gathering statistics for ALL services of the app...")
    lines = get_docker_stats()
    
    # Target containers
    targets = {'spring-backend', 'ai-brain', 'mongodb', 'redis-cache', 'next-frontend'}
    
    data = []
    for line in lines:
        if not line: continue
        parts = line.split(',')
        if len(parts) >= 3:
            name = parts[0]
            if name in targets or any(t in name for t in targets):
                cpu_str = parts[1].replace('%', '')
                try:
                    cpu = float(cpu_str)
                except ValueError:
                    cpu = 0.0
                
                # MemUsage looks like "152.3MiB / 7.595GiB"
                mem_raw = parts[2].split('/')[0].strip()
                mem_val = 0.0
                if 'MiB' in mem_raw:
                    mem_val = float(mem_raw.replace('MiB', ''))
                elif 'GiB' in mem_raw:
                    mem_val = float(mem_raw.replace('GiB', '')) * 1024
                elif 'KiB' in mem_raw:
                    mem_val = float(mem_raw.replace('KiB', '')) / 1024
                elif 'B' in mem_raw:
                    mem_val = float(mem_raw.replace('B', '')) / (1024 * 1024)
                
                data.append({'Service Component': name, 'CPU Usage (%)': cpu, 'Memory Usage (MiB)': mem_val})

    df = pd.DataFrame(data)
    if df.empty:
        print("No metrics found. Are the containers running?")
        return
        
    print("\n--- Current System Resources for App Services ---")
    print(df.to_string(index=False))
    
    # Generate Chart
    fig, axes = plt.subplots(ncols=2, figsize=(14, 6))
    
    # Plot CPU
    df.sort_values('CPU Usage (%)', ascending=False).plot(
        kind='bar', x='Service Component', y='CPU Usage (%)', 
        color='#d9534f', ax=axes[0], legend=False
    )
    axes[0].set_title('CPU Usage per Service (%)')
    axes[0].set_ylabel('CPU %')
    axes[0].tick_params(axis='x', rotation=45)
    
    # Plot Memory
    df.sort_values('Memory Usage (MiB)', ascending=False).plot(
        kind='bar', x='Service Component', y='Memory Usage (MiB)', 
        color='#5bc0de', ax=axes[1], legend=False
    )
    axes[1].set_title('Memory Usage per Service (MB)')
    axes[1].set_ylabel('Memory (MB)')
    axes[1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig('system_hardware_metrics.png')
    plt.close()
    print("\nSystem-wide statistics generation completed!")
    print("Hardware chart saved as system_hardware_metrics.png")

if __name__ == "__main__":
    generate_system_metrics()
