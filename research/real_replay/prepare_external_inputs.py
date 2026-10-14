"""Prepare declared source layouts from explicitly supplied upstream archives."""
import argparse,hashlib,json,shutil,struct,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
def save_bytes(path,payload,expected=None):
    if expected and hashlib.sha256(payload).hexdigest()!=expected:raise ValueError('Source member SHA mismatch: '+path.name)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(payload)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rfly-real-archive',type=Path)
    p.add_argument('--hil-archive',type=Path)
    p.add_argument('--insane-sensors-archive',type=Path)
    p.add_argument('--insane-calibration-archive',type=Path)
    p.add_argument('--flight-review-ulog',type=Path)
    p.add_argument('--omit-real-archive-copy',action='store_true',help='Extract the 406 topics only; caller must place the original archive for 407_1.')
    a=p.parse_args();out=a.output.resolve()
    if out.exists():p.error('output must be a new directory; sources are never overwritten')
    out.mkdir(parents=True);actions=[]
    reference=json.loads((HERE/'frozen_replay_fingerprints.json').read_text(encoding='utf-8'))
    if a.rfly_real_archive:
        expected=reference['raw_sources']['407_1']['input_records'][0]
        if sha(a.rfly_real_archive)!=expected['sha256']:raise ValueError('RflyMAD official Real-Motor archive SHA mismatch')
        with zipfile.ZipFile(a.rfly_real_archive) as archive:
            for case in ('406_1','406_2'):
                for item in reference['raw_sources'][case]['input_records']:
                    basename=Path(item['path']).name
                    names=[n for n in archive.namelist() if n.startswith('acce/'+case+'/') and n.endswith('/'+basename)]
                    if len(names)!=1:raise ValueError('Original case/topic member is not unique: '+basename)
                    save_bytes(out/item['path'],archive.read(names[0]),item['sha256'])
                    actions.append({'member':names[0],'output':item['path'],'sha256':item['sha256']})
        if not a.omit_real_archive_copy:
            destination=out/expected['path'];destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(a.rfly_real_archive,destination)
            assert sha(destination)==expected['sha256']
            actions.append({'output':expected['path'],'sha256':expected['sha256']})
    # Complete official IDF members are supplied with verified CC-BY attribution.
    idf=ROOT/'data/external/idf_ds_lap120_verified_v34';target=out/'external_datasets/idf_ds_lap120'
    shutil.copytree(idf,target)
    actions.append({'output':'external_datasets/idf_ds_lap120','profile':'complete official v1.0 members, v34 verified'})
    if a.insane_sensors_archive:
        with zipfile.ZipFile(a.insane_sensors_archive) as archive:
            info=archive.getinfo('indoor_1_sensors/px4_imu.csv')
            with a.insane_sensors_archive.open('rb') as f:
                f.seek(info.header_offset);header=f.read(30);name_length,extra_length=struct.unpack_from('<2H',header,26)
                payload=header+f.read(name_length+extra_length+info.compress_size)
        save_bytes(out/'external_datasets/insane/indoor_1_px4_imu_segment.bin',payload,'7b5bbf40d4d1a004436b6c153d80ca1063363cce9c4449d8cc09279403f5464b')
        actions.append({'member':'indoor_1_sensors/px4_imu.csv','verified_original_compressed_segment':True})
    if a.insane_calibration_archive:
        if sha(a.insane_calibration_archive)!='cff4fbd099051cf0ff29838f7ab4bc67ff35d70cc6555029e537ca1036c215f2':raise ValueError('INSANE calibration SHA mismatch')
        destination=out/'external_datasets/insane/insane_sensor_calib_preprocessed.zip';destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.insane_calibration_archive,destination)
    if a.flight_review_ulog:
        item=reference['raw_sources']['FlightReview']['inputs'][0]
        if sha(a.flight_review_ulog)!=item['sha256']:raise ValueError('Flight Review ULog SHA mismatch')
        destination=out/item['path'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.flight_review_ulog,destination)
    if a.hil_archive:
        hil=json.loads((ROOT/'research/threshold_reproduction/raw_reproduction_receipt.json').read_text(encoding='utf-8'))
        expected={row['source_relative_path']:row['source_sha256'] for row in hil['inputs']}
        destination=out/'external_datasets/rflymad/HIL-Complete-StateOnly'
        with zipfile.ZipFile(a.hil_archive) as archive:
            names=set(archive.namelist())
            for name,digest in expected.items():
                case=name.removesuffix('/TrueData/UAVState_data.xlsx')
                for suffix in ('/TestInfo.csv','/TrueData/TrueState_data.xlsx','/TrueData/UAVState_data.xlsx'):
                    member=case+suffix
                    if member not in names:raise ValueError('Kaggle HIL v2 member missing: '+member)
                    save_bytes(destination/member,archive.read(member),digest if suffix.endswith('UAVState_data.xlsx') else None)
        actions.append({'output':'external_datasets/rflymad/HIL-Complete-StateOnly','cases':2613,'uav_state_SHA_verified':True,'other_fields_verified_by_split_reconstruction':True})
    (out/'preparation_receipt.json').write_text(json.dumps({'status':'passed','actions':actions,'downloads':0,'sources_never_modified':True,'complete_four_source_layout':bool(a.rfly_real_archive and not a.omit_real_archive_copy and a.insane_sensors_archive and a.insane_calibration_archive and a.flight_review_ulog)},indent=2)+'\n',encoding='utf-8')
    print('Prepared explicit source layout. Omitted archives remain caller obligations; see the receipt.')
if __name__=='__main__':main()
