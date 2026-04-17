import sys
import iris

def get_connection():
    """
    Establish a connection if we are running externally (Native API).
    If we are running purely sequentially inside IRIS (Embedded Python),
    this will return None as we don't need a Native API connection.
    """
    if not bool(getattr(sys, "_embedded", 0)):
        print("[Demo] Running externally. Establishing Native API connection...")
        try:
            import iris
        except ImportError:
            print("Error: The 'intersystems_iris' package is required for remote execution.")
            print("Install it with: pip install intersystems_iris")
            sys.exit(1)
            
        # Customize these connection parameters for your environment
        host = "localhost"
        port = 1972
        namespace = "USER"
        user = "SuperUser"
        password = "SYS"
        
        try:
            conn = iris.createConnection(host, port, namespace, user, password)
            db = iris.createIRIS(conn)
            print("[Demo] Connected successfully via Native API.")
            return db
        except Exception as e:
            print(f"[Demo] Connection failed: {e}")
    else:
        print("[Demo] Running inside IRIS (Embedded Python).")
        return None

def run_demo():
    print("\n--- Starting ObjectScript Demonstration ---")
    
    try:
        # Example 1: Instantiating an ObjectScript class via _New (mapped to %New)
        # Using Ens.StringRequest since it's available on all instances
        print("\n1. Instantiating a StringRequest...")
        dyn_obj = iris.cls("Ens.StringRequest")._New()
        
        # Example 2: Property assignment (Native API: set(oref, name, value))
        print("2. Setting properties...")
        dyn_obj.StringValue = "Hello, InterSystems IRIS!"
        print(f"   StringValue set to: {dyn_obj.StringValue}")
        
        
        # Example 4: Method invocation (mapped from _Save to %Save)
        print("4. Invoking instance method (_Save)...")
        json_output = dyn_obj._Save()
        print(f"   Output: {json_output}")
        
        # Example 5: Class Method invocation
        print("\n5. Invoking a Class Method (HostName)...")
        hostname = iris.cls("%SYSTEM.INetInfo").LocalHostName()
        print(f"   HostName: {hostname}")
        
    except Exception as e:
        print(f"\n[Demo] Error during execution: {e}")

if __name__ == "__main__":
    # 1. Initialize DB connection (None if embedded)
    db_conn = get_connection()
    
    # 2. Register connection to iris_embedded_python unified wrapper
    if db_conn is not None:
        iris.set_active_connection(db_conn)
        
    # 3. Run the exact same codebase regardless of context!
    run_demo()
