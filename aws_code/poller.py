import boto3
import time
import subprocess
import os

BUCKET_NAME = "rorabucket"
CHECK_INTERVAL = 10  # seconds
LAMBDA_IP = "209.20.159.84"  # replace if needed

seen_files = set()

def main():
    s3 = boto3.client("s3")

    print(f"[EC2] Watching S3 bucket: {BUCKET_NAME}")
    while True:
        try:
            response = s3.list_objects_v2(Bucket=BUCKET_NAME)
            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    if key.lower().endswith((".mov", ".mp4")) and key not in seen_files:
                        print(f"[EC2] New video detected in S3: {key}")
                        seen_files.add(key)

                        # Download locally
                        local_path = f"/tmp/{os.path.basename(key)}"
                        s3.download_file(BUCKET_NAME, key, local_path)
                        print(f"[EC2] Downloaded {key} to {local_path}")

                        # Send to Lambda server
                        print(f"[EC2] Sending {local_path} → Lambda:{LAMBDA_IP}:/home/ubuntu/input_videos/")
                        subprocess.run([
                            "scp", "-i", "/home/ec2-user/.ssh/id_rsa",
                            local_path, f"ubuntu@{LAMBDA_IP}:/home/ubuntu/input_videos/"
                        ], check=True)

                        print(f"[EC2] Transfer complete: {key} → Lambda")

        except Exception as e:
            print(f"[EC2] Error:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
