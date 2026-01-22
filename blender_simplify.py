"""
Blender script for model simplification using decimation.
Usage: blender -b -P blender_simplify.py -- <model_path> <reduction_ratio>
Based on working Blender script console approach.
Writes progress to a log file for real-time monitoring.
"""

import sys
import os


def simplify_model(model_path, reduction_ratio, log_file=None, options=None):
    """Simplify a GLB/GLTF model using Blender's decimation modifier."""
    
    import bpy
    
    options = options or {}
    
    def log(msg):
        """Print and optionally write to file."""
        print(msg)
        if log_file:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except:
                pass
    
    model_path = os.path.abspath(model_path)
    
    log(f"Blender version: {bpy.app.version_string}")
    log(f"Model: {model_path}")
    log(f"Decimation ratio: {reduction_ratio}")
    
    # Remove default scene objects
    log("Clearing default scene...")
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Import the GLB
    log("Importing GLB model...")
    try:
        bpy.ops.import_scene.gltf(filepath=model_path)
        log("Model imported successfully")
    except Exception as e:
        log(f"ERROR: Import failed: {e}")
        return False
    
    # Pre-processing: merge by distance and remove duplicates
    if options.get("preprocess", True):
        log("Pre-processing: merging nearby vertices...")
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH':
                continue
            
            try:
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                # Merge vertices within 0.0001 units
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold=0.0001)
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
            except Exception as e:
                log(f"  WARNING: {obj.name} pre-process failed: {e}")
                bpy.ops.object.mode_set(mode='OBJECT')
    
    # Categorize meshes
    log("Analyzing mesh complexity...")
    MIN_TRIANGLES = 500
    
    # First pass: identify meshes to merge (under MIN_TRIANGLES)
    small_meshes = []
    large_meshes = []
    
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        
        mesh = obj.data
        tri_count = len(mesh.polygons)
        
        if tri_count < MIN_TRIANGLES:
            small_meshes.append(obj)
        else:
            large_meshes.append(obj)
    
    log(f"Found {len(small_meshes)} small meshes and {len(large_meshes)} large meshes")
    
    def merge_mesh_group(mesh_group, label):
        """Join a group of meshes into one, return merged object or None."""
        if not mesh_group:
            return None
        bpy.ops.object.select_all(action='DESELECT')
        for obj in mesh_group:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_group[0]
        try:
            bpy.ops.object.join()
            merged_mesh = mesh_group[0]
            log(f"  {label}: merged into {merged_mesh.name}")
            return merged_mesh
        except Exception as e:
            log(f"  WARNING: {label} merge failed: {e}")
            return None

    # Merge small meshes together if there are any
    if len(small_meshes) > 0:
        # Batch merges to avoid overly heavy single join in large scenes
        MERGE_BATCH_SIZE = 50
        log(f"Merging {len(small_meshes)} small meshes in batches of {MERGE_BATCH_SIZE}...")
        merged_groups = []
        for i in range(0, len(small_meshes), MERGE_BATCH_SIZE):
            batch = small_meshes[i:i + MERGE_BATCH_SIZE]
            merged = merge_mesh_group(batch, f"Small batch {i // MERGE_BATCH_SIZE + 1}")
            if merged:
                merged_groups.append(merged)
            else:
                # Fall back to individual meshes when merge fails
                merged_groups.extend(batch)

        # Add merged groups to large meshes for simplification
        large_meshes.extend(merged_groups)
    
    # Second pass: advanced simplification on all meshes
    simplified_count = 0
    if not options.get("advanced_simplify", True):
        log("Skipping advanced simplification (disabled)")
        large_meshes = []
    else:
        log(f"Applying advanced simplification to {len(large_meshes)} mesh(es)...")
    
    for obj in large_meshes:
        mesh = obj.data
        tri_count_before = len(mesh.polygons)
        
        # Apply decimation modifier
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # Main decimation
            dec = obj.modifiers.new(name="Decimate", type='DECIMATE')
            dec.decimate_type = 'COLLAPSE'
            dec.ratio = reduction_ratio
            dec.use_collapse_triangulate = True
            
            bpy.ops.object.modifier_apply(modifier=dec.name)
            
            if options.get("delete_loose", True) or options.get("smooth_normals", False):
                # Remove loose geometry (CAD models often have internal/stray faces)
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                if options.get("delete_loose", True):
                    bpy.ops.mesh.delete_loose()
                
                # Smooth normals for better shading
                if options.get("smooth_normals", False):
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.average_normals()
            
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.select_set(False)
            
            simplified_count += 1
            simplified_count += 1
        except Exception as e:
            log(f"    ERROR: {e}")
            bpy.ops.object.mode_set(mode='OBJECT')
    
    log(f"Simplified {simplified_count} meshes")
    
    # Export the result
    log("Exporting simplified GLB...")
    try:
        bpy.ops.export_scene.gltf(
            filepath=model_path,
            export_format='GLB',
            export_apply=True
        )
        log("Export successful")
        return True
    except Exception as e:
        log(f"ERROR: Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point for the script."""
    # Extract arguments after '--'
    if '--' not in sys.argv:
        print("ERROR: No arguments provided. Usage: blender -b -P blender_simplify.py -- <model_path> <reduction_ratio>")
        return False
    
    args = sys.argv[sys.argv.index('--') + 1:]
    
    if len(args) < 2:
        print("ERROR: Missing arguments. Usage: blender -b -P blender_simplify.py -- <model_path> <reduction_ratio> [options]")
        return False
    
    model_path = args[0]
    try:
        reduction_ratio = float(args[1])
    except ValueError:
        print(f"ERROR: Invalid reduction ratio: {args[1]}")
        return False

    # Optional flags
    opts = {
        "preprocess": True,
        "advanced_simplify": True,
        "delete_loose": True,
        "smooth_normals": False,
    }
    for arg in args[2:]:
        if arg == "--no-preprocess":
            opts["preprocess"] = False
        elif arg == "--no-advanced":
            opts["advanced_simplify"] = False
        elif arg == "--no-delete-loose":
            opts["delete_loose"] = False
        elif arg == "--smooth":
            opts["smooth_normals"] = True
    
    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found: {model_path}")
        return False
    
    # Create log file in same directory as model
    log_file = model_path + ".simplify.log"
    
    # Clear log file
    try:
        open(log_file, 'w').close()
    except:
        log_file = None
    
    print(f"Starting simplification...")
    print(f"  Model: {model_path}")
    print(f"  Reduction ratio: {reduction_ratio}")
    if log_file:
        print(f"  Log file: {log_file}")
    
    success = simplify_model(model_path, reduction_ratio, log_file, options=opts)
    
    if success:
        print("Simplification completed successfully")
        return True
    else:
        print("Simplification failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
