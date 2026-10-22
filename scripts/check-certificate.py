#!/usr/bin/env python3
"""Check hostname and expiry in separate OpenSSL invocations."""
import argparse,json,os,subprocess

def check(certificate,hostname,seconds=604800):
    env=dict(os.environ,LC_ALL='C')
    base=['openssl','x509','-in',str(certificate),'-noout']
    try:
        host=subprocess.run(base+['-checkhost',hostname],capture_output=True,text=True,env=env,timeout=10)
        expiry=subprocess.run(base+['-checkend',str(seconds)],capture_output=True,text=True,env=env,timeout=10)
        # Some OpenSSL versions return zero even for a hostname mismatch.
        host_ok=host.returncode==0 and 'does match certificate' in host.stdout
        expiry_ok=expiry.returncode==0
        return {'valid':host_ok and expiry_ok,'hostname_valid':host_ok,'expiry_valid':expiry_ok,'hostname':hostname,'hostname_result':host.stdout.strip(),'expiry_result':expiry.stdout.strip()}
    except (OSError,subprocess.TimeoutExpired):
        return {'valid':False,'hostname_valid':False,'expiry_valid':False,'hostname':hostname,'error':'Certificate validation could not run'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('certificate');p.add_argument('hostname');p.add_argument('--seconds',type=int,default=604800);a=p.parse_args()
    result=check(a.certificate,a.hostname,a.seconds);print(json.dumps(result));raise SystemExit(0 if result['valid'] else 1)
