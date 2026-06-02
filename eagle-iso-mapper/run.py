# run.py
import sys
import subprocess
from pathlib import Path

def generate_models():
    """
    Programmatically generates Pydantic models from the LinkML YAML.
    Using the native Python API avoids cross-platform CLI path issues (especially on Windows).
    """
    try:
        from linkml.generators.pydanticgen import PydanticGenerator
    except ImportError:
        print("❌ Error: LinkML is not installed. Please run 'uv add linkml'.")
        sys.exit(1)

    yaml_path = Path("src/model/eagle-lcml-mapping.linkml.yaml")
    output_path = Path("src/python/generated/eagle_iso_models.py")

    if not yaml_path.exists():
        print(f"⚠️ Warning: YAML file not found at {yaml_path}. Skipping generation.")
        return

    print(f"📦 Generating Pydantic models from {yaml_path}...")

    # Ensure the target directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Initialize the generator and serialize the YAML to Python code
        generator = PydanticGenerator(str(yaml_path))
        generated_code = generator.serialize()

        # Write the generated code to the target file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(generated_code)

        print(f"✅ Models successfully generated at {output_path}")
    except Exception as e:
        print(f"❌ Fatal error during model generation: {e}")
        sys.exit(1)

def main():
    """
    Main entry point: Generates the models, then boots up the Streamlit UI.
    """
    print("🚀 Starting build and boot process...")

    # Step 1: Build the data models from YAML
    generate_models()

    # Step 2: Launch the Streamlit application
    print("🌐 Launching Streamlit App...")
    try:
        # Uses the current Python executable (controlled by uv) to start Streamlit
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Streamlit exited with an error: {e}")

if __name__ == "__main__":
    main()
