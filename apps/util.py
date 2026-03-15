import json

from apps.universities.models import PerguruanTinggi as PT, ProgramStudi as PS, DataMahasiswa as DM, DataDosen as DD


def load_json_data(file_path = 'apps/ept_itpt.json'):
    # Replace 'data.json' with the path to your JSON file
    # file_path = 'apps/ept_itpt.json'

    try:
        with open(file_path, 'r') as file: 
            data_dict = json.load(file)
        return data_dict
    
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from the file. Check if the file is correctly formatted.")
    return None


def load_mstodb(START=0, END=1):
    data_dict = load_json_data('apps/ept_itms.json')
    if data_dict is None:
        print("No data to load into the database.")
        return
    else:
        print("Jumlah record : {}".format(len(data_dict)))
    N=START
    for item in data_dict[START:END]:
        o = {}
        f = item['fields']
        s = str( f['semester'] )
        o['tahun_akademik'] =  s.split(' ')[0]
        o['semester'] =  s.split(' ')[1]
        o['mahasiswa_aktif'] =  f['jumlah']

        o['kodept'] =  f['kodept']
        o['kodeps'] =  f['kodeps']

        PT_ID = 0
        PS_ID = 0
        r = PT.objects.filter(kode_pt=o['kodept'])
        if len(r)>0:
            PT_ID = r[0].id
            p = PS.objects.filter(kode_prodi=o['kodeps'], perguruan_tinggi_id=PT_ID)
            if len(p)>0:
                PS_ID = p[0].id
                
                
        o['pt_id']  = PT_ID
        o['ps_id']  = PS_ID
        
        ms = DM.objects.values('id').filter(
            perguruan_tinggi_id=PT_ID, 
            program_studi_id = PS_ID,
            tahun_akademik = o['tahun_akademik'],
            semester = o['semester'])
        if len( ms )>0:
            m = DM.objects.get(pk=ms[0]['id'])
        else:
            m = DM()
            m.perguruan_tinggi_id = PT_ID
            m.program_studi_id = PS_ID

        m.tahun_akademik = o['tahun_akademik']
        m.semester = o['semester']
        m.mahasiswa_aktif = o['mahasiswa_aktif']

        if not( (PT_ID==0) or  (PS_ID==0) ):
            m.save()
            print("No: {}|{}".format(N,o) )
        else:
            print("PS_ID: {} | PT_ID={}".format(PS_ID, PT_ID))

        print("===============================================")
        N = N + 1
        



def load_pstodb(START=0, END=1):
    data_dict = load_json_data('apps/ept_itps.json')
    if data_dict is None:
        print("No data to load into the database.")
        return
    else:
        print("Jumlah prodi : {}".format(len(data_dict)))

    rs = PT.objects.all().values('id','kode_pt','nama')
    for r in rs[START:END]:
        
        print("{}|{}".format(r['kode_pt'],r['nama']) )
              
        KODEPT = r['kode_pt']
        PT_ID = r['id']

        for item in data_dict:

            f = item['fields']               
            if f['kodept']==KODEPT:
                print( "pt|ps: {}|{}".format( f['kodept'], f['kodeps'] )  )

                # periksa kodeps                  
                ps = PS.objects.filter(perguruan_tinggi_id=PT_ID, kode_prodi=f['kodeps']).values('id')
                if len(ps)>0:
                    msg='update'
                    p = PS.objects.get(pk=ps[0]['id'])
                else:
                    msg='insert'
                    p = PS(kode_prodi=f['kodeps'])
                    p.perguruan_tinggi_id = PT_ID
                
                p.nama = f['namaps']
                p.jenjang = f['jenjang']
                p.akreditasi = f['akreditasi']
                p.is_active = ( f['status']=='Aktif' )
                
                try:
                    p.save()
                    print( "{} > Data Program Studi {}".format(msg,f['namaps']))
                except Exception as e:
                    print("Ada kesalahan saat menyimpan data: {}".format(e))

    pass

def load_data_to_db(START=0,END=1):
    data_dict = load_json_data()
    if data_dict is None:
        print("No data to load into the database.")
        return

    for item in data_dict[START:END]:
        
        f = item['fields']               
        p = json.loads( f['pt'] )
                
        rs = PT.objects.filter(kode_pt=f['kodept'])
        if len(rs)<1:
            sth  = p['noskberdiri']
            sth = sth[-4:]

            # Create or update the PerguruanTinggi instance
            pt, created = PT.objects.update_or_create(
                kode_pt = f['kodept'],
                nama = f['namapt'],
                singkatan = "-", #f['singkatan'],
                jenis = f['jenis'],
                organisasi_induk = f['organisasi'],
                wilayah_id = 1,
                # Lokasi
                alamat = p['alamat'],
                kota = "-", #f['kota'],
                provinsi = "-", #f['provinsi'],
                kode_pos = "-", #f['kode_pos'],
                # latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
                # longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
                
                # Kontak
                website = p['website'],
                email = p['email'],
                telepon = p['telepon'],
                
                # Akreditasi
                akreditasi_institusi = f['akreditasi'],
                # nomor_sk_akreditasi = models.CharField(max_length=100, blank=True)
                # tanggal_sk_akreditasi = models.DateField(null=True, blank=True)
                # tanggal_kadaluarsa_akreditasi = models.DateField(null=True, blank=True)
                
                # Status
                is_active = (p['status'] == 'Aktif'), 
                tahun_berdiri = int(sth) if sth.isdigit() else None,
                # logo = models.ImageField(upload_to='logos/', null=True, blank=True)
            )
            
            if created:
                print(f"Created new PerguruanTinggi: {f['namapt']} (Kode: {f['kodept']})")
            else:
                print(f"Updated existing PerguruanTinggi: {f['namapt']} (Kode: {f['kodept']})") 
        
        else:
            print(f"PerguruanTinggi with Kode PT {f['kodept']} already exists. Skipping creation.")
            
            # update status dan akreditasi
            r = PT.objects.get(pk=rs.first().id)
            r.is_active = (p['status'] == 'Aktif')
            
            if f['akreditasi'] in ['unggul','Unggul']:
                r.akreditasi_institusi = r.StatusAkreditasi.UNGGUL     
            if f['akreditasi']=='Baik Sekali':
                r.akreditasi_institusi = r.StatusAkreditasi.BAIK_SEKALI
            if f['akreditasi'] in ['Baik', 'Terakreditasi','B']:
                r.akreditasi_institusi = r.StatusAkreditasi.BAIK
            if f['akreditasi'] == 'Tidak Terakreditasi':
                r.akreditasi_institusi = r.StatusAkreditasi.BELUM

            if f['organisasi'] in ['Muhammadiyah']:
                r.organisasi_induk = r.OrganisasiInduk.MUHAMMADIYAH
            if f['organisasi'] in ['Aisyiyah',"'Aisyiyah"]:
                r.organisasi_induk = r.OrganisasiInduk.AISYIYAH
            
            if f['jenis'] in ['Universitas']:
                r.jenis = r.JenisPT.UNIVERSITAS
            if f['jenis'] in ['Institut']:
                r.jenis = r.JenisPT.INSTITUT
            if f['jenis'] in ['Sekolah Tinggi']:
                r.jenis = r.JenisPT.SEKOLAH_TINGGI
            if f['jenis'] in ['Politeknik']:
                r.jenis = r.JenisPT.POLITEKNIK
            if f['jenis'] in ['Akademi']:
                r.jenis = r.JenisPT.AKADEMI
            
            try:
                r.save()
                print( 'Update Sukses')
            except Exception as e:
                print( 'Ada kesalahan saat menyimpan.')





def data_test():
    x = load_json_data()
    if x is None:
        print("Failed to load data from JSON file.")
    else:
        f = x[0]['fields']
        print( f['kodept'] )

    
