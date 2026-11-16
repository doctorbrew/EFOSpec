"""Exercise real PyRAF Tk cursor events on a disposable saved standard aperture.

This validates the toolkit event path, not a human's physical mouse operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/'runs/pyraf-debug/full1d-03'
    image=next(source.glob('tvma2*61358_1.fits'))
    aperture=source/'database'/('ap'+image.stem)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'database').mkdir();(out/'cache').mkdir()
    for src,dst in [(image,out/image.name),(aperture,out/'database'/aperture.name)]:shutil.copy2(src,dst)
    original=aperture.read_bytes()
    image_hash=hashlib.sha256(image.read_bytes()).hexdigest()
    os.environ.pop('PYRAF_NO_DISPLAY',None)
    os.environ['iraf']='/usr/local/lib/iraf/'
    os.environ['PYRAF_CLCACHE_PATH']=str(out/'cache')
    os.chdir(out)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('Editor exceeded 60 seconds')))
    signal.alarm(60)
    from pyraf import iraf,gkigcur
    iraf.noao(_doprint=0);iraf.twodspec(_doprint=0);iraf.apextract(_doprint=0)
    iraf.apextract.dispaxis=2
    # World positions are in the existing standard aperture's spatial pixels.
    events=iter([('l',443.8643),('u',456.8643),('b',449.8643),
                 ('z',-30.),('z',30.),
                 ('s',-35.),('s',-25.),('s',25.),('s',35.),
                 ('f',0.),('q',0.),('q',449.8643),
                 ('d',500.),('f',500.),('q',500.)])
    evidence=[]
    original_start=gkigcur.Gcursor.startCursorMode
    original_key=gkigcur.Gcursor.getKey
    # Ignore physical keystrokes during this automated test only. Tk-generated
    # events still traverse the real binding, cursor conversion and IRAF IPC.
    sending=False
    def test_key(cursor,event):
        if sending:
            return original_key(cursor,event)
    gkigcur.Gcursor.getKey=test_key
    def start(cursor):
        key,wx=next(events)
        def send():
            nonlocal sending
            cursor.window.wcs.commit()
            record=cursor.window.wcs.wcs[0]
            wx1,wx2,wy1,wy2,sx1,sx2,sy1,sy2,xt,yt,flag=record
            x=sx1+(wx-wx1)/(wx2-wx1)*(sx2-sx1);y=(sy1+sy2)/2
            gw=cursor.gwidget
            gw.focus_force()
            gw.event_generate('<Motion>',x=int(x*gw.width),y=int((1-y)*gw.height))
            gw.moveCursorTo(x*gw.width,y*gw.height,SWmove=1)
            sending=True
            try:gw.event_generate('<KeyPress>',keysym=key,when='now')
            finally:sending=False
        timer=cursor.top.after(250,send)
        try:result=original_start(cursor)
        finally:cursor.top.after_cancel(timer)
        assert result.split()[3]==key, result
        assert abs(float(result.split()[0])-wx)<0.01, result
        evidence.append({'key':key,'requested_world_x':wx,'returned_cursor':result})
        print(evidence[-1],flush=True)
        return result
    gkigcur.Gcursor.startCursorMode=start
    try:
        iraf.apedit(image.name,find='no',recenter='no',resize='no',edit='yes',interactive='yes',line=200,nsum=10,Stdin=['yes\n']*20)
        iraf.aptrace(image.name,interactive='yes',find='no',edit='no',trace='yes',fittrace='yes',line=200,nsum=10,step=10,function='legendre',order=6,Stdin=['yes\n']*20)
        iraf.apall(image.name,output='edited_extraction.fits',interactive='no',find='no',recenter='no',resize='no',edit='no',trace='no',fittrace='no',extract='yes',extras='yes',format='multispec',background='fit',weights='variance',readnoise=11.,gain=1.18)
    finally:
        gkigcur.Gcursor.startCursorMode=original_start
        gkigcur.Gcursor.getKey=original_key
        signal.alarm(0)
    updated=(out/'database'/aperture.name).read_text()
    import re
    assert abs(float(re.search(r'\n\s*low\s+(\S+)',updated)[1])+6)<0.01
    assert abs(float(re.search(r'\n\s*high\s+(\S+)',updated)[1])-7)<0.01
    sample=re.search(r'\n\s*sample\s+([^\n]+)',updated)[1]
    bounds=[tuple(map(float,pair.split(':'))) for pair in sample.split()]
    assert bounds==[(-35.,-25.),(25.,35.)]
    from astropy.io import fits
    import numpy as np
    data=fits.getdata(out/'edited_extraction.fits')
    assert data.shape==(4,1,1015) and np.isfinite(data).all()
    assert aperture.read_bytes()==original
    assert hashlib.sha256(image.read_bytes()).hexdigest()==image_hash
    assert updated.split('\tcurve')[1] != original.decode().split('\tcurve')[1]
    (out/'editor-events.json').write_text(json.dumps({'events':evidence,'source_aperture_sha256':hashlib.sha256(original).hexdigest(),'edited_aperture':updated,'source_image_sha256':image_hash,'extracted_shape':list(data.shape),'all_pixels_finite':True,'human_mouse_test':False},indent=2)+'\n')
    print('Saved',out/'editor-events.json')

if __name__=='__main__':main()
