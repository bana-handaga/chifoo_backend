## Modifikasi Desember 2024
## untuk mengambil data beberapa semester

from selenium import webdriver
import selenium.webdriver.firefox.firefox_binary
import selenium.webdriver.firefox.firefox_profile


from selenium.webdriver.firefox.options import Options as OptFitefox
from selenium.webdriver.firefox.service import Service as SvcFitefox
from webdriver_manager.firefox import GeckoDriverManager

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


from django.db.models import Max, Min, Q, F
from bs4 import BeautifulSoup as bs
import requests as req
import json

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def GetEdge():
    driver = webdriver.Edge()
    return driver

def getProfile():
    profile = webdriver.FirefoxProfile()
    profile.set_preference("browser.privatebrowsing.autostart", True)
    return profile

def GetFirefox():
    options = Options()
    options.add_argument('--start-maximized')
    #options = OptFitefox()
    #options.add_argument('--headless')
    #options.add_argument('--no-sandbox')
    #options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.maximize_window()
    
    browser = webdriver.Firefox()
    return browser

def GetDriver():
    options = Options()
    options.add_argument('--start-maximized')
    # options.add_argument('--headless')
    # options.add_argument('--no-sandbox')
    #options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.maximize_window()
    return driver

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

## DETAIL PT 
def PTGetDetail(idsp="aAO7n5JVAkq7CRxD8guoM59cyIpDHCq06vX2HpidUwHmR4GNSeXdURhOw9fAYm2g8_ovdQ=="):
    
    TIME_OUT = 60

    L= 'https://pddikti.kemdikbud.go.id/api/pt/detail/'
    res = req.get(L+idsp, timeout=TIME_OUT)
    if res.status_code==200:
        o = res.json()
        print( o )

def GoPTGetDetail():
    
    ###############
    rs = Tpt.objects.values('kodept','id','idsp')
    if len(rs)>0:
        N = 1
        for r in rs:
            kodept = r['kodept']
            print( '[{}] {}'.format( N, kodept ) )
            if len( r['idsp'] )>=72:
                L = PTGetDetail(r['idsp'])

            N = N+1
    #############

def OpenPTPage(d, namapt='Universitas Muhammadiyah Surakarta'):

    xp = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[1]/div[1]/div[1]/input'
    btnPATH = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[1]/div[1]/div[2]'
    
    try:
        element = WebDriverWait(d, 12).until( 
            EC.presence_of_all_elements_located(By.XPATH,)
        )
    except:
        pass

    PTNAME = namapt
    d.find_element(By.XPATH, xp).send_keys(PTNAME)
    d.find_element(By.XPATH,btnPATH).click()

    rpath = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[2]/div'
    rPT = d.find_element(By.XPATH,rpath)
    if PTNAME in rPT.text: 
        # ada
        detailPATH = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[2]/div[1]/div[4]/div/button[1]'
        rPT.find_element(By.XPATH,detailPATH).click()


from ept.models import FTpt, Tpt, Tps, Tds
import time
from selenium.webdriver.support.ui import Select
from django.db.models import Q


TIME_WAIT = 10

def getElement(DRIVER,MYXPATH,TW=TIME_WAIT):
    try:
        # EC.element_to_be_clickable((By.XPATH,MYXPATH))
        element = WebDriverWait(DRIVER, TW).until(
                EC.element_to_be_clickable((By.XPATH,MYXPATH))
        )
        return DRIVER.find_element(By.XPATH,MYXPATH)
    except Exception as e:   
        print('Error get Clickable - {}', format(e))
        return None

def getElementDisplay(DRIVER,MYXPATH,TW=TIME_WAIT):
    try:
        element = WebDriverWait(DRIVER, TW).until(
                EC.presence_of_element_located((By.XPATH,MYXPATH))
        )
        return DRIVER.find_element(By.XPATH,MYXPATH)
    except Exception as e:   
        print('Error get display - {}', format(e))
        return None

def getElementLengkap(DRIVER,MYXPATH,TW=TIME_WAIT):
    try:
        element = WebDriverWait(DRIVER, TW).until(
                EC.presence_of_element_located((By.XPATH,MYXPATH))
        )
        return DRIVER.find_element(By.XPATH,MYXPATH)
    except Exception as e:   
        print('Error located - {}', format(e))
        return None
    
SEMESTER = 20252    # for STpt  - 09 Maret 2026

from ept.models import ITpt, ITps, ITdd, ITms
from _pt.models import STpt, STps, STdd, STms


UPDATE_PRODI = False

### 1 ##>
def synctoSTpt_ITpt(START=0,STOP=1):
    dbPT = ITpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = ITpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows = STpt.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rept_tpt = STpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tpt = STpt()
            action = "INSERT"

        rept_tpt.kodept = rpt.kodept
        rept_tpt.namapt = rpt.namapt
        rept_tpt.jenis =  rpt.jenis
        rept_tpt.organisasi = rpt.organisasi
        rept_tpt.akreditasi =  rpt.akreditasi
        rept_tpt.status =  rpt.status

        rept_tpt.pt = rpt.pt
        rept_tpt.ps = rpt.ps
        rept_tpt.ds = rpt.ds
        rept_tpt.ms = rpt.ms
        rept_tpt.idsp = "-"
        rept_tpt.semester = 20252

                
        try:
            rept_tpt.save()
            print("{:4}|{} ept_tpt - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} ept_tpt - GAGAL - {}".format(N, action,e))

        N = N+1




def sTpt2sTms(START=0,STOP=1):
    dbPT = STpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = STpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            MHS = json.loads( rpt.ms )
        except:
            MHS = rpt.ms
        
        if KODEPT in MHS:
            for KODEPS in MHS[KODEPT]:
                rows = STps.objects.values('id').filter(
                    kodept=KODEPT, kodeps=KODEPS
                )
                if len(rows)>0:
                    rps = STps.objects.get(pk=rows[0]['id'])

                for mhs in MHS[KODEPT][KODEPS]['mahasiswa']:
                    rows = STms.objects.values('id').filter(
                        kodept=KODEPT,kodeps=KODEPS,semester=mhs['semester']
                    )
                    if len(rows)>0:
                        rmhs = STms.objects.get(pk=rows[0]['id'])
                        action = 'UPDATE'
                    else:
                        rmhs = STms()
                        action = 'SIMPAN'
                    rmhs.kodept = KODEPT
                    rmhs.kodeps = KODEPS
                    rmhs.semester = mhs['semester']
                    rmhs.jumlah = int( mhs['mahasiswa'] )
                    rmhs.tahun = int( str(mhs['semester'])[0:4] )
                    rmhs.jenjang = rps.jenjang
                    rmhs.Tpt = rpt
                    rmhs.Tps = rps

                    try:
                        rmhs.save()
                        print("{} data mahasiswa/semester - SUKSES - {}|{}|{}:{}".format(
                            action, rmhs.kodept, rmhs.kodeps, rmhs.semester, rmhs.jumlah
                        ))
                    except Exception as e:
                        print("Simpan/update data mahasiswa/semester - GAGAL - {}".format(e))


#########################
## TAHAP-2 UPDATE DETAIL DOSEN
## 09 Maret 2026
def dosen_detail(DRIVER, dsn={},rpt=None, rps=None, SEMESTER=20252):
    #d = GetDriver() 

    print("-------------------------------")
    print( dsn )
    print("-------------------------------")

    DRIVER.get( dsn['linkdosen'] )
    time.sleep(2)
    rds = {}
    DETAIL_DOSEN = False
    TRIAL = 0
    while not DETAIL_DOSEN and TRIAL<5:
        try:
            DSN_DETAIL = getElementLengkap(DRIVER,'/html/body/div[1]/div/div[4]/div[3]/div',30)    
            DETAIL_DOSEN = True
        except:
            print('Tabel detail dosen belum muncul')
            time.sleep(1)
            TRIAL =+ 1

    rds = {}

    rds['nama']       = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[1]/p[2]').text.strip()
    while rds['nama']=='...':
        rds['nama']       = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[1]/p[2]').text.strip()
        time.sleep(1)
    
    #while rds['nama']=='-':
    #    rds['nama']       = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[1]/p[2]').text.strip()
    #    time.sleep(1)

    rds['gender']     = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[2]/p[2]').text.strip()
    rds['namapt']     = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[3]/p[2]').text.strip()
    rds['namaps']     = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[4]/p[2]').text.strip()
    rds['jabfung']    = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[5]/p[2]').text.strip()
    rds['pendidikan'] = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[6]/p[2]').text.strip()
    rds['statuskerja']= DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[7]/p[2]').text.strip()
    rds['statusaktif']= DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[3]/div/div/div[8]/p[2]').text.strip()
    
    sekolah = []
    table = DRIVER.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div[1]/div/table/tbody')                                        
    if not (table is None):
        rows = table.find_elements(By.XPATH,'.//tr')
        if len(rows)>0:                                                                                                        
            for r in rows:
                cs = r.find_elements(By.XPATH,'.//td')
                if len(cs)>0:
                    nc = 0
                    out={}
                    for c in cs:
                        if nc==0:
                            out['pt'] = c.text.strip()
                        elif nc==1:
                            out['gelar'] = c.text.strip()
                        elif nc==2:
                            out['tahun'] = c.text.strip()
                        elif nc==3:                                                   
                            out['jenjang'] = c.text.strip()                        
                        nc = nc+1  
                sekolah.append( out )

    rds['sekolah'] = sekolah
    print("MENYUSUN DATA DOSEN")
    
    rows = STdd.objects.values('id').filter(
        kodept=dsn['kodept'],kodeps=dsn['kodeps'],nama=dsn["nama"],pendidikan=rds['pendidikan']
        )

    #if not dsn['linkdosen'] is None:
    #    rows = ITdd.objects.values('id').filter(linkdosen=rds['linkdosen'])
    #else:

    if len(rows)>0:
        msg = 'UPDATE'
        rdsn = STdd.objects.get(pk=rows[0]['id'])
    else:
        msg = 'INSERT'
        rdsn = STdd()  

    KODEPT = dsn['kodept']
    KODEPS = dsn['kodeps']
    rdsn.kodept = KODEPT
    rdsn.kodeps = KODEPS
    
    rdsn.namapt = rds['namapt']
    if rds['namapt']=='-':
        rdsn.namapt = dsn['ptma']
    rdsn.namaps = rds['namaps']
    if rds['namaps']=='-':
        rdsn.namaps = dsn['prodi']    
    rdsn.nama = rds['nama']
    if rds['nama']=='-':
        rdsn.nama = dsn['nama']

    rdsn.jk = rds['gender'][0]
    rdsn.pendidikan = rds['pendidikan']
    rdsn.fungsional = rds['jabfung']
    rdsn.ikatankerja = rds['statuskerja']
    rdsn.statuskeaktifan = rds['statusaktif']
    rdsn.sekolah = rds['sekolah']
    rdsn.nidn = dsn["nidn"]
    rdsn.gelar = dsn["nuptk"]
    rdsn.linkdosen = dsn['linkdosen']

    rdsn.Tpt = rpt
    rdsn.Tps = rps
    #rdsn.S20232 = 0
    #rdsn.S20241 = 0
    rdsn.S20252 = 1
    '''
    if SEMESTER==20252:
        rdsn.S20252 = 1
    if SEMESTER==20251:
        rdsn.S20251 = 1        
    if SEMESTER==20242:
        rdsn.S20242 = 1
    if SEMESTER==20241:
        rdsn.S20241 = 1
    if SEMESTER==20232:
        rdsn.S20232 = 1
    if SEMESTER==20231:
        rdsn.S20231 = 1
    if SEMESTER==20222:
        rdsn.S20222 = 1
    if SEMESTER==20221:
        rdsn.S20221 = 1
    if SEMESTER==20212:
        rdsn.S20212 = 1
    if SEMESTER==20211:
        rdsn.S20211 = 1
    if SEMESTER==20202:
        rdsn.S20202 = 1
    if SEMESTER==20201:
        rdsn.S20201 = 1

    '''

    try:
        rdsn.save()
        print("{} DATA DETAIL DOSEN - SUKSES".format(msg))
        print( rds )
    except Exception as e:
        print("SIMPAN DATA DETAIL DOSEN GAGAL - {}".format(e))

    #DRIVER.close()

#########################
## TAHAP-2 UPDATE DETAIL DOSEN
## 06 Juni 2025
## 042010|62201|Akuntansi
## YOGI RAHMAN FERIZA GINTING

def syncSTpt2STdd(START=0,STOP=1, PTKODE='ALL', NAME='ALL', DRV=0, ND='NAMA', SEMESTER=20252):

    if DRV==0:
        d = GetDriver()
        DRIVER = GetDriver()    
    
    if DRV==2:
        d = GetFirefox()
        DRIVER = GetFirefox()

    if DRV==1:
        d = GetEdge()
        DRIVER = GetEdge()

    dbPT = STpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')    

    MULAI_BACA_DATA = False   # membaca dadetail dosen
    # MULAI_BACA_DATA = True

    GONEXT = False
    for kpt in dbPT[START:STOP]:
        try:
            pt = STpt.objects.get(pk=kpt['id'])

            if kpt['kodept'] in ['042010','065004','023138','213137','133053']:                
                continue

            

            # jum to target PTMA with KODEPT ============
            if not (PTKODE=='ALL'):
                if kpt['kodept']==PTKODE:
                    GONEXT = True
                if not GONEXT==True:
                    continue
            # =============================================
            

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        
        try:
            PRODI = json.loads( pt.ps )
        except:
            PRODI = pt.ps

        try:
            DSN = json.loads( pt.ds )
        except:
            DSN = pt.ds

        
        #print("--------------------------------")
        #print( DSN )
        #print("--------------------------------")
        
        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )

        

        for KODEPT in DSN:

            

            #print( KODEPT )
            UPDATE_PRODI = False
            for KODEPS in DSN[KODEPT]:
                #print( KODEPS )
                
                rows = STps.objects.values('id').filter(kodept=KODEPT, kodeps=KODEPS, semester=SEMESTER)
                if len(rows)>0:
                    rps = STps.objects.get(pk=rows[0]['id'])

                NAMA2_DOSEN = []
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        NAMA_PRODI = NAMA_PRODI.replace("(","").replace(")","").replace("'","")
                        break 

                print( '# DOSEN HOMEBASE ')
                
                if 'homebase' in DSN[KODEPT][KODEPS]: 
                    
                    
                    NEXTNAME = False
                    for dsnhomebase in DSN[KODEPT][KODEPS]['homebase']:

                        if not (NAME=='ALL'):
                            # Jump to target NAME    
                            if not dsnhomebase['nama'] == NAME:
                                continue
                            else:
                                NAME = 'ALL'
                                
                        
                        # MULAI_BACA_DATA = False
                        MULAI_BACA_DATA = True
                        
                        print("-------------------------------------")
                        print("### NAMA DOSEN: {} ###".format(dsnhomebase['nama']) )
                        NAMADOSEN =  str(dsnhomebase['nama']).strip().replace(' ','%20').upper()
                        
                        # CROSS CHECK
                        rcs = ITdd.objects.filter(
                            kodept=KODEPT, nama=dsnhomebase['nama'],
                            pendidikan=dsnhomebase['pendidikan']
                        )
                        if len(rcs)>0:
                            MULAI_BACA_DATA = True
                        elif ND in dsnhomebase['nama']:
                            MULAI_BACA_DATA = True
                        


                        print('MULAI_BACA_DATA : {}'.format(MULAI_BACA_DATA))


                        if not MULAI_BACA_DATA:
                            continue

                        #if not dsnhomebase['nama'].upper() in ["ADRIAL"]:
                        #    continue


                        NIDN = "-"
                        NUPTK = "-"
                        if 'nidn' in dsnhomebase:
                            NIDN = dsnhomebase['nidn']
                        if 'nuptk' in dsnhomebase:                            
                            NUPTK = dsnhomebase['nuptk']
                        

                        NAMADOSEN = NAMADOSEN.replace("(","").replace(")","").replace("'","")
                        
                        NAMAPT = str(pt.namapt).strip().replace(' ','%20').upper()
                        NAMAPT = NAMAPT.replace("(","").replace(")","").replace("'","")

                        #LDSN = "https://pddikti.kemdikbud.go.id/search/" + NAMADOSEN  + '%20' + NAMAPT
                        LDSN = "https://pddikti.kemdiktisaintek.go.id/search/" + NAMADOSEN  + '%20' + NAMAPT

                        NAMA_DOSEN = str(dsnhomebase['nama']).strip().replace("(","").replace(")","").replace("'","")

                        print( LDSN )
                        
                        #d.get( 'https://pddikti.kemdiktisaintek.go.id' )      
                        d.get( LDSN )      

                        DOSEN_SHOW = False
                        TRAIL = 0
                        while not DOSEN_SHOW and TRAIL<5:
                            try:
                                DOSEN_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[1]/div/div',20)
                                DOSEN_SHOW = True
                            except:
                                print("Wait for Dosen lable")
                                time.sleep(1)
                                TRAIL =+ 1
                        

                        try:
                            if 'Dosen' in DOSEN_LABEL.text.strip():


                                PAGES_DOSEN = False
                                PAGE_TRIAL = 0
                                while not PAGES_DOSEN and PAGE_TRIAL<3:
                                    print( 'TRIAL: {}'.format(PAGE_TRIAL))
                                    try:
                                        WAIT_PAGE_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]',10)    
                                        #print( WAIT_PAGE_LABEL.text )
                                        PAGES = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]')
                                        #print( PAGES.text )
                                        PAGES_DOSEN = True
                                    except:
                                        print("Wait for PAGES")
                                        PAGE_TRIAL =  PAGE_TRIAL + 1
                                        time.sleep(1)                                        
                                    
                                        if PAGE_TRIAL>1:
                                                try:
                                                    
                                                    NO_RESULT = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[2]/div/div/div/div/p[1]',10)
                                                    if 'Tidak ada' in NO_RESULT.text.strip():
                                                        break
                                                    else:
                                                        print( 'Tunggu check 5x')
                                                except:
                                                    pass
                                
                                print( 'TRIAL: {}'.format(PAGE_TRIAL))
                                if PAGE_TRIAL>=3:
                                    break

                                MAXPAGE = 0
                                try:
                                    MAXPAGE = int(PAGES.text.strip())
                                except:
                                    pass

                                NPAGE = 0
                                out = []
                                while NPAGE<MAXPAGE:                                
                                    table = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/table/tbody')                                    
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:                                                                                            
                                            n = 1
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['nama'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==1:
                                                            dsn['ptma'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==2:
                                                            dsn['prodi'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==3:                                                   
                                                            # print ( c.find_element(By.TAG_NAME,'a').get_attribute("href") )
                                                            dsn['linkdosen'] = c.find_element(By.TAG_NAME,'a').get_attribute("href")
                                                            print( 'LINK ODSEN: {}'.format(dsn['linkdosen']))
                                                        nc = nc+1   
                                                    
                                                    NAMAPT = pt.namapt.upper().strip().replace("(","").replace(")","").replace("'","")
                                                    
                                                    print( 'PTMA: {}'.format(NAMAPT))
                                                    print( 'PTMA: {}'.format(dsn['ptma']))


                                                    if  dsn['ptma'] == NAMAPT:
                                                        print( "### data dsn: {}".format( dsn ))
                                                        print('PRODI: {}'.format(NAMA_PRODI.upper()))
                                                        print('NAMA_DOSEN: {}'.format(NAMA_DOSEN.upper()))

                                                        if dsn['prodi'] == NAMA_PRODI.upper():
                                                                if dsn['nama'] == NAMA_DOSEN.upper():
                                                                    dsn['kodept'] = KODEPT
                                                                    dsn['kodeps'] = KODEPS
                                                                    dsn['nidn'] = NIDN
                                                                    dsn['nuptk'] = NUPTK
                                                                    out.append( dsn )
                                                                    NAMA2_DOSEN.append(NAMA_DOSEN.upper())
                                                                    dosen_detail( DRIVER, dsn, pt, rps )
                                                                    break
                                                n = n+1
                                    if len(out)==0:
                                        d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/button[2]').click()
                                        NPAGE = NPAGE + 1
                                    else:
                                        break                                                                                                                                                        
                                print( out )
                                    

                        except Exception as e:
                            print("Error cari Dosen - {}".format(e))
                        #    # pass
                        




                        time.sleep(2)



        
#########################
## TAHAP-2 UPDATE DETAIL DOSEN
## 06 Juni 2025

def update_dsn(dsn={},rpt=None,rps=None,SEMESTER=20252,NOMOR=1):
    
    #print("-------------------------------")
    #print( dsn )
    #print("-------------------------------")
    
    #print("Lihat Tabel DOSEN")
    rows = ITdd.objects.values('id').filter(
        kodept=rpt.kodept,nama=dsn['nama'],pendidikan=dsn['pendidikan'],S20251=1
        ) 
    if len(rows)<1:
        rdsn = ITdd()  

        rdsn.kodept = rpt.kodept
        rdsn.kodeps = rps.kodeps
        #rpt = ITpt.objects.filter(kodept=dsn['kodept'],semester=SEMESTER)
        rdsn.namapt = rpt.namapt 
        #rps = ITps.objects.filter(kodept=dsn['kodept'],kodeps=dsn['kodeps'],semester=SEMESTER)
        rdsn.namaps = rps.namaps
        rdsn.nama = dsn['nama']
        rdsn.pendidikan = dsn['pendidikan']
        rdsn.ikatankerja = dsn['ikatankerja']
        rdsn.statuskeaktifan = dsn['status']
        rdsn.nidn = dsn["nidn"]
        rdsn.gelar = dsn["nuptk"]
        rdsn.S20251 = 1
        rdsn.tempat_lahir = '-'

        rdsn.Tpt_id = rpt.pk
        rdsn.Tps_id = rps.pk
        
        '''
        if SEMESTER==20252:
            rdsn.S20252 = 1
        if SEMESTER==20251:
            rdsn.S20251 = 1        
        if SEMESTER==20242:
            rdsn.S20242 = 1
        if SEMESTER==20241:
            rdsn.S20241 = 1
        if SEMESTER==20232:
            rdsn.S20232 = 1
        if SEMESTER==20231:
            rdsn.S20231 = 1
        if SEMESTER==20222:
            rdsn.S20222 = 1
        if SEMESTER==20221:
            rdsn.S20221 = 1
        if SEMESTER==20212:
            rdsn.S20212 = 1
        if SEMESTER==20211:
            rdsn.S20211 = 1
        if SEMESTER==20202:
            rdsn.S20202 = 1
        if SEMESTER==20201:
            rdsn.S20201 = 1
        '''

        try:
            rdsn.save()
            print("-------------------------------------")
            print("### NAMA DOSEN: {}:{}:{}:{} ###".format(dsn['nama'],rps.kodeps,rpt.kodept,rpt.namapt) )
            print("-------------------------------------")
            print( dsn )
            print("SIMPAN DOSEN SHORT - SUKSES")
            
        except Exception as e:
            print("SIMPAN DOSEN GAGAL - {}".format(e))
        
        # print('{:5} > OK'.format(NOMOR))        
        print('{:5} > {} BELUM ADA di tabel '.format( dsn['nama'], NOMOR))
    else:
        r = ITdd.objects.get(pk=rows[0]['id'])
        r.kodept = rpt.kodept
        r.kodeps = rps.kodeps
        r.namapt = rpt.namapt 
        r.namaps = rps.namaps
        r.tempat_lahir = '-'
        try:
            r.save()
            print('{:5} UPDATE TEMPAT_LAHIR > OK'.format(NOMOR))
        except Exception as e:
            print('ERROR Database connection: '.format(e) )

def checkDosenITpt_on_ITdd(KODEPT='011003', START=0,STOP=1, SEMESTER=20252):


    dbPT = ITpt.objects.filter(semester=SEMESTER,kodept=KODEPT).values('id','kodept').order_by('-organisasi', 'namapt')
    NOMOR = 1

    for kpt in dbPT[START:STOP]:
        pt = ITpt.objects.get(pk=kpt['id'])

        try:
            PRODI = json.loads( pt.ps )
        except:
            PRODI = pt.ps

        try:
            DSN = json.loads( pt.ds )
        except:
            DSN = pt.ds
        
        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )        

        for KODEPT in DSN:
            UPDATE_PRODI = False
            for KODEPS in DSN[KODEPT]:
                rows = ITps.objects.values('id').filter(kodept=KODEPT, kodeps=KODEPS, semester=SEMESTER)
                if len(rows)>0:
                    rps = ITps.objects.get(pk=rows[0]['id'])

                NAMA2_DOSEN = []
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        #print('')
                        #print('')
                        #print('#############################################')
                        #print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        #print('#############################################')
                        NAMA_PRODI = NAMA_PRODI.replace("(","").replace(")","").replace("'","")
                        
                        break 

                print( '# DOSEN HOMEBASE: {} {}'.format( rps.kodeps, rps.namaps ))
                
                if 'homebase' in DSN[KODEPT][KODEPS]: 
                    for dsnhomebase in DSN[KODEPT][KODEPS]['homebase']:
                        #print("-------------------------------------")
                        #print("### NAMA DOSEN: {}:{}:{}:{} ###".format(dsnhomebase['nama'],rps.kodeps,pt.kodept,pt.namapt) )
                        
                        update_dsn(dsnhomebase,pt,rps,NOMOR)
                        # print( dsnhomebase['nama'] )

                        NOMOR = NOMOR + 1                      

#########################
## TAHAP-2 UPDATE DETAIL DOSEN
## 06 Juni 2025 --- NO NEED
def checkGTdd_2_HTdd(START=0,STOP=1,SEMESTER=20252):
    dbPT = ITpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            pt = ITpt.objects.get(pk=kpt['id'])
        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )

        # check ststus aktif di Sem 20241       
        rds = HTdd.objects.filter(kodept=pt.kodept,S20251=1)
        if len(rds)>0:
            for ds in rds:
              print('============')
              print('{}-{}-{}-{}'.format(ds.kodept,ds.kodeps,ds.nama,ds.pendidikan))
              rds = GTdd.objects.filter(kodept=ds.kodept,kodeps=ds.kodeps,nama=ds.nama,pendidikan=ds.pendidikan)
              
              if len(rds)<0:
                  print('Dosen ini Tidak aktif di sem 20241' )
                  #r = HTdd.objects.get(pk=ds.pk)
                  #r.S20241 = 0
                  #r.save()

              print('============')
                                
def dosen_satu(MKODEPT="061008",DOSENNAMA=""):
    d = GetDriver()
    DRIVER = GetDriver()    
    # dbPT = ITpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    dbPT = ITpt.objects.values('id','kodept').filter(kodept=MKODEPT)
    for kpt in dbPT:
        try:
            pt = ITpt.objects.get(pk=kpt['id'])

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PRODI = json.loads( pt.ps )
        except:
            PRODI = pt.ps

        try:
            DSN = json.loads( pt.ds )
        except:
            DSN = pt.ds

        
        #print("--------------------------------")
        #print( DSN )
        #print("--------------------------------")
        
        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )
        for KODEPT in DSN:
            #print( KODEPT )
            UPDATE_PRODI = False
            for KODEPS in DSN[KODEPT]:
                #print( KODEPS )
                
                rows = GTps.objects.values('id').filter(kodept=KODEPT, kodeps=KODEPS)
                if len(rows)>0:
                    rps = GTps.objects.get(pk=rows[0]['id'])

                NAMA2_DOSEN = []
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        NAMA_PRODI = NAMA_PRODI.replace("(","").replace(")","").replace("'","")
                        break 

                print( '# DOSEN HOMEBASE ')
                if 'homebase' in DSN[KODEPT][KODEPS]: 
                    for dsnhomebase in DSN[KODEPT][KODEPS]['homebase']:
                        print("-------------------------------------")
                        print("### NAMA DOSEN: {} ###".format(dsnhomebase['nama']) )
                        NAMADOSEN =  str(dsnhomebase['nama']).strip().replace(' ','%20').upper()

                        if not dsnhomebase['nama']==DOSENNAMA:
                            continue


                        NIDN = "-"
                        NUPTK = "-"
                        if 'nidn' in dsnhomebase:
                            NIDN = dsnhomebase['nidn']
                        if 'nuptk' in dsnhomebase:                            
                            NUPTK = dsnhomebase['nuptk']
                        

                        NAMADOSEN = NAMADOSEN.replace("(","").replace(")","").replace("'","")
                        
                        NAMAPT = str(pt.namapt).strip().replace(' ','%20').upper()
                        NAMAPT = NAMAPT.replace("(","").replace(")","").replace("'","")

                        LDSN = "https://pddikti.kemdikbud.go.id/search/" + NAMADOSEN  + '%20' + NAMAPT

                        NAMA_DOSEN = str(dsnhomebase['nama']).strip().replace("(","").replace(")","").replace("'","")

                        print( LDSN )
                        d.get( LDSN )                                                
                        DOSEN_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[1]/div/div',20)
                        try:
                            if 'Dosen' in DOSEN_LABEL.text.strip():
                                WAIT_PAGE_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]',30)    
                                PAGES = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]')
                                MAXPAGE = int(PAGES.text.strip())
                                NPAGE = 0
                                out = []
                                while NPAGE<MAXPAGE:                                
                                    table = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/table/tbody')                                    
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:                                                                                            
                                            n = 1
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['nama'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==1:
                                                            dsn['ptma'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==2:
                                                            dsn['prodi'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==3:                                                   
                                                            # print ( c.find_element(By.TAG_NAME,'a').get_attribute("href") )
                                                            dsn['linkdosen'] = c.find_element(By.TAG_NAME,'a').get_attribute("href")
                                                        nc = nc+1   
                                                    
                                                    NAMAPT = pt.namapt.upper().strip().replace("(","").replace(")","").replace("'","")
                                                    if  dsn['ptma'] == NAMAPT:
                                                        # print( "### data dsn: {}".format( dsn ))
                                                        if dsn['prodi'] == NAMA_PRODI.upper():
                                                                if dsn['nama'] == NAMA_DOSEN.upper():
                                                                    dsn['kodept'] = KODEPT
                                                                    dsn['kodeps'] = KODEPS
                                                                    dsn['nidn'] = NIDN
                                                                    dsn['nuptk'] = NUPTK
                                                                    out.append( dsn )
                                                                    NAMA2_DOSEN.append(NAMA_DOSEN.upper())
                                                                    dosen_detail( DRIVER, dsn, pt, rps )
                                                                    break
                                                n = n+1
                                    if len(out)==0:
                                        d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/button[2]').click()
                                        NPAGE = NPAGE + 1
                                    else:
                                        break                                                                                                                                                        
                                print( out )
                                    

                        except Exception as e:
                            print("Error cari Dosen - {}".format(e))
                        #    # pass
                        




                        time.sleep(2)

# update data satu dosen
def update_ds_satu(START=0,STOP=1):
    #rs = GTdd.objects.filter(S20241=1).order_by('namapt')
    rs = GTdd.objects.filter(nidn="-").order_by('kodept','kodeps')
    print ( len(rs) )
    if len(rs)>0:
        for r in rs[START:STOP]:
            print( "{}|{}".format(r.kodept,r.nama) )
            dosen_satu(r.kodept, r.nama)

def check_dosen_pt(MKODEPT="061008"):
    d = GetDriver()
    DRIVER = GetDriver()    
    # dbPT = ITpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    dbPT = ITpt.objects.values('id','kodept').filter(kodept=MKODEPT)
    for kpt in dbPT:
        try:
            pt = ITpt.objects.get(pk=kpt['id'])

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PRODI = json.loads( pt.ps )
        except:
            PRODI = pt.ps

        try:
            DSN = json.loads( pt.ds )
        except:
            DSN = pt.ds

        
        #print("--------------------------------")
        #print( DSN )
        #print("--------------------------------")
        
        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )
        for KODEPT in DSN:
            #print( KODEPT )
            UPDATE_PRODI = False
            for KODEPS in DSN[KODEPT]:
                #print( KODEPS )
                
                rows = GTps.objects.values('id').filter(kodept=KODEPT, kodeps=KODEPS)
                if len(rows)>0:
                    rps = GTps.objects.get(pk=rows[0]['id'])

                NAMA2_DOSEN = []
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        NAMA_PRODI = NAMA_PRODI.replace("(","").replace(")","").replace("'","")
                        break 

                print( '# DOSEN HOMEBASE ')
                if 'homebase' in DSN[KODEPT][KODEPS]: 
                    for dsnhomebase in DSN[KODEPT][KODEPS]['homebase']:
                        print("-------------------------------------")
                        print("### NAMA DOSEN: {} ###".format(dsnhomebase['nama']) )
                        NAMADOSEN =  str(dsnhomebase['nama']).strip().replace(' ','%20').upper()

                        rdsn_in_ftdd = ITdd.objects.filter(kodept=MKODEPT, nama=dsnhomebase['nama'],nidn__isnull=True)
                        if len(rdsn_in_ftdd)<1:
                            continue


                        NIDN = "-"
                        NUPTK = "-"
                        if 'nidn' in dsnhomebase:
                            NIDN = dsnhomebase['nidn']
                        if 'nuptk' in dsnhomebase:                            
                            NUPTK = dsnhomebase['nuptk']
                        

                        NAMADOSEN = NAMADOSEN.replace("(","").replace(")","").replace("'","")
                        
                        NAMAPT = str(pt.namapt).strip().replace(' ','%20').upper()
                        NAMAPT = NAMAPT.replace("(","").replace(")","").replace("'","")

                        LDSN = "https://pddikti.kemdikbud.go.id/search/" + NAMADOSEN  + '%20' + NAMAPT

                        NAMA_DOSEN = str(dsnhomebase['nama']).strip().replace("(","").replace(")","").replace("'","")

                        print( LDSN )
                        d.get( LDSN )                                                
                        DOSEN_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[1]/div/div',20)
                        try:
                            if 'Dosen' in DOSEN_LABEL.text.strip():
                                WAIT_PAGE_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]',30)    
                                PAGES = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]')
                                MAXPAGE = int(PAGES.text.strip())
                                NPAGE = 0
                                out = []
                                while NPAGE<MAXPAGE:                                
                                    table = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/table/tbody')                                    
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:                                                                                            
                                            n = 1
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['nama'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==1:
                                                            dsn['ptma'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==2:
                                                            dsn['prodi'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==3:                                                   
                                                            # print ( c.find_element(By.TAG_NAME,'a').get_attribute("href") )
                                                            dsn['linkdosen'] = c.find_element(By.TAG_NAME,'a').get_attribute("href")
                                                        nc = nc+1   
                                                    
                                                    NAMAPT = pt.namapt.upper().strip().replace("(","").replace(")","").replace("'","")
                                                    if  dsn['ptma'] == NAMAPT:
                                                        # print( "### data dsn: {}".format( dsn ))
                                                        if dsn['prodi'] == NAMA_PRODI.upper():
                                                                if dsn['nama'] == NAMA_DOSEN.upper():
                                                                    dsn['kodept'] = KODEPT
                                                                    dsn['kodeps'] = KODEPS
                                                                    dsn['nidn'] = NIDN
                                                                    dsn['nuptk'] = NUPTK
                                                                    out.append( dsn )
                                                                    NAMA2_DOSEN.append(NAMA_DOSEN.upper())
                                                                    dosen_detail( DRIVER, dsn, pt, rps )
                                                                    break
                                                n = n+1
                                    if len(out)==0:
                                        d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/button[2]').click()
                                        NPAGE = NPAGE + 1
                                    else:
                                        break                                                                                                                                                        
                                print( out )
                                    

                        except Exception as e:
                            print("Error cari Dosen - {}".format(e))
                        #    # pass
                        




                        time.sleep(2)

# update data satu dosen
def check_ds_satu(START=0,STOP=1):

    dPT = ITpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dPT[START:STOP]:
        pt = ITpt.objects.get(pk=kpt['id'])
        check_dosen_pt(pt.kodept)

########################################
## TAHAP-2    Maret 2025
## UPDATE BUKAN DOSEN PRODI | sepertinya sudah tidak perlu

def dosen_rasio(START=0,STOP=1):
    d = GetDriver()
    DRIVER = GetDriver()    
    dbPT = HTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            pt = HTpt.objects.get(pk=kpt['id'])

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PRODI = json.loads( pt.ps )
        except:
            PRODI = pt.ps

        try:
            DSN = json.loads( pt.ds )
        except:
            DSN = pt.ds
        print("--------------------------------------------")
        print("#### PTMA: {} ###".format( pt.namapt ) )
        for KODEPT in DSN:
            #print( KODEPT )
            UPDATE_PRODI = False
            for KODEPS in DSN[KODEPT]:
                #print( KODEPS )
                
                rows = HTps.objects.values('id').filter(kodept=KODEPT, kodeps=KODEPS)
                if len(rows)>0:
                    rps = HTps.objects.get(pk=rows[0]['id'])

                NAMA2_DOSEN = []
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        print("#")
                        print("----------------------####-------------------------")
                        print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        NAMA_PRODI = NAMA_PRODI.replace("(","").replace(")","").replace("'","")
                        break 
                
                print( '# DOSEN PENGHITUNG RASIO ')
                if 'rasio' in DSN[KODEPT][KODEPS]: 
                    for dsnrasio in DSN[KODEPT][KODEPS]['rasio']:

                        NIDN = dsnrasio["nidn"]
                        #Jika sudah ada di htdd lanjutkan iterasi
                        if len(NIDN)==10:
                            rows = HTdd.objects.values('id').filter(
                                kodept=KODEPT,
                                nidn=NIDN
                            )
                        else:    
                            rows = HTdd.objects.values('id').filter(
                                kodept=KODEPT, kodeps=KODEPS,
                                nama=NAMA_DOSEN.upper()
                            )
                            if len(rows)<1:
                                rows = HTdd.objects.values('id').filter(
                                    kodept=KODEPT,
                                    nama=NAMA_DOSEN.upper()
                                ).exclude(kodeps=KODEPS)

                        if len(rows)>0:
                            print("# DOSEN RASIO ## sudah ada di HTDD => Lanjut ke DOSEN BERIKUTNYA")
                            continue
  

                        print("-------------------------------------")
                        print("### NAMA DOSEN: {} ###".format(dsnrasio['nama']) )
                        NAMADOSEN =  str(dsnrasio['nama']).strip().replace(' ','%20').upper()

                        NAMADOSEN = NAMADOSEN.replace("(","").replace(")","").replace("'","")
                        
                        NAMAPT = str(pt.namapt).strip().replace(' ','%20').upper()
                        NAMAPT = NAMAPT.replace("(","").replace(")","").replace("'","")

                        LDSN = "https://pddikti.kemdikbud.go.id/search/" + NAMADOSEN  + '%20' + NAMAPT

                        NAMA_DOSEN = str(dsnrasio['nama']).strip().replace("(","").replace(")","").replace("'","")

                        print( LDSN )
                        d.get( LDSN )                                                
                        DOSEN_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[1]/div/div',20)
                        try:
                            if 'Dosen' in DOSEN_LABEL.text.strip():
                                WAIT_PAGE_LABEL = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]',30)    
                                PAGES = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/div/p[2]')
                                MAXPAGE = int(PAGES.text.strip())
                                NPAGE = 0
                                out = []
                                while NPAGE<MAXPAGE:                                
                                    table = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/table/tbody')                                    
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:                                                                                            
                                            n = 1
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['nama'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==1:
                                                            dsn['ptma'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==2:
                                                            dsn['prodi'] = c.text.strip().replace("(","").replace(")","").replace("'","")
                                                        elif nc==3:                                                   
                                                            # print ( c.find_element(By.TAG_NAME,'a').get_attribute("href") )
                                                            dsn['linkdosen'] = c.find_element(By.TAG_NAME,'a').get_attribute("href")
                                                        nc = nc+1   
                                                    
                                                    NAMAPT = pt.namapt.upper().strip().replace("(","").replace(")","").replace("'","")
                                                    if  dsn['ptma'] == NAMAPT:
                                                        if dsn['nama'] == NAMA_DOSEN.upper():
                                                            if len(NIDN)==10:
                                                                rows = HTdd.objects.values('id').filter(
                                                                    kodept=KODEPT, kodeps=KODEPS,
                                                                    nidn=NIDN
                                                                )
                                                            else:    
                                                                rows = HTdd.objects.values('id').filter(
                                                                    kodept=KODEPT, kodeps=KODEPS,
                                                                    nama=NAMA_DOSEN.upper()
                                                                )                                                            
                                                            if len(rows)>0:
                                                                print(' {} sudah terdaftar di homebase'.format(NAMA_DOSEN))
                                                            else:
                                                                #cari di prodi yang lain
                                                                if len(NIDN)==10:
                                                                    rows = HTdd.objects.values('id','namaps').filter(
                                                                        kodept=KODEPT,  nidn=NIDN
                                                                    ).exclude(kodeps=KODEPS)
                                                                else:
                                                                    rows = HTdd.objects.values('id','namaps').filter(
                                                                        kodept=KODEPT,  nama=NAMA_DOSEN.upper()
                                                                    ).exclude(kodeps=KODEPS)
                                                                if len(rows)>0:
                                                                    #rrasio = FTdd.objects.get(pk=rows[0]['id'])
                                                                    print('dosen # {} # sudah terdaftar di prodi # {}'.format(NAMA_DOSEN,rows[0]['namaps']))
                                                                else:
                                                                    dsn['kodept'] = KODEPT
                                                                    dsn['kodeps'] = KODEPS
                                                                    out.append( dsn )
                                                                    #NAMA2_DOSEN.append(NAMA_DOSEN.upper())
                                                                    dosen_detail( DRIVER, dsn, pt, rps )
                                                                    print("Tambahkan DOSEN BARU # {}".format(NAMA_DOSEN))
                                                                    print( out )
                                                            break
                                                n = n+1

                                    # periksa sampai ketemu DOSEN yang dicari
                                    if len(out)==0:
                                        d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[4]/div/div[2]/div/div/button[2]').click()
                                        NPAGE = NPAGE + 1
                                    else:
                                        break                                                                                                                                                        
                                    
                                    

                        except Exception as e:
                            print("Error cari Dosen rasio - {}".format(e))
                    
                        time.sleep(1)        

########################################
## TAHAP-2    JUNI 2025  semester
## TAHAP-2    Maret 2025
## UPDATE PROFILE PRODI
########################################
#def ps_profile(START=0,STOP=1):
def syncSTpt2STps(START=0,STOP=1):    ## TAHAP-2 JUNI 2025 SYNC from ITpt to ITps

    #dbPT = ITpt.objects.filter(Q(kodept='051022')|Q(kodept='091004')|Q(kodept='061004')|Q(kodept='101018')|
    #                              Q(kodept='071024')|Q(kodept='161018')|Q(kodept='021004')|Q(kodept='051007')|                                  
    #                              Q(kodept='081010')).values('id','kodept').order_by('-organisasi','namapt') 

    dbPT = STpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = STpt.objects.get(pk=kpt['id'])
        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PRODI = json.loads( rpt.ps )
        except:
            PRODI = rpt.ps

        try:
            DSN = json.loads( rpt.ds )
        except:
            DSN = rpt.ds    

        print("## PTMA: # {}".format( rpt.namapt ) )
        for KODEPT in DSN:
            #print( KODEPT )
            for KODEPS in DSN[KODEPT]:
                #print( KODEPS )
                NAMA_PRODI = ''
                for rPS in PRODI[KODEPT]: 
                    if rPS['pskode']==KODEPS:
                        NAMA_PRODI = rPS['ps']
                        print("### {}|{}|{}".format(KODEPT, KODEPS, NAMA_PRODI))
                        break 
                try:
                    PROFILE = DSN[KODEPT][KODEPS]['profile']
                    rows = ITps.objects.values('id').filter(kodept=KODEPT,kodeps=KODEPS, semester=rpt.semester)
                    if len(rows)>0:
                        rps = STps.objects.get(pk=rows[0]['id'])
                        msg = 'UPDATE'
                    else:
                        rps = STps()
                        msg = 'INSERT'
                    
                    
                    rps.ps = PROFILE
                    rps.kodept = KODEPT
                    rps.kodeps = KODEPS
                    rps.namaps = NAMA_PRODI
                    rps.semester = rpt.semester #SEMESTER
                    rps.jenjang = PROFILE['jenjang']
                    rps.status = PROFILE['status']
                    rps.akreditasi = PROFILE['akreditasi']
                    rps.akreditasi_internasional = PROFILE['akreditasi_inter'] 
                    rps.dosen_rasio = PROFILE['dsrasio']
                    rps.nidn = PROFILE['nidn']
                    rps.nidk = PROFILE['nidk']
                    rps.total = PROFILE['total']
                    rps.mahasiswa = PROFILE['mhs']
                    rps.dosen_homebase = int(PROFILE['nidn']) + int(PROFILE['nidk']) 
                    rps.rasio = PROFILE['rasio']
                    rps.Tpt = rpt
                    try:
                        rps.save()
                        print("{} detail Prodi - SUKSES".format(msg))
                    except Exception as e:
                        print("{} detail Prodi - GAGAL - {}".format(msg,e))
                except Exception as e:
                    print("Tidak ada profile prodi ... continue")

########################################
## TAHAP-2    Maret 2025
## UPDATE STATUS PTMA
########################################

def syncSTpt_sts(START=0,STOP=1):
    dbPT = STpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = STpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PT = json.loads( rpt.pt )
        except:
            PT = rpt.pt
        
        try:
            rpt.status = PT['status']
            rpt.akreditasi = PT['akreditasi']
            rpt.save()
            print("UPDATE status|akreditasi - SUKSES - {}|{} -#- {}".format(
                rpt.kodept, rpt.namapt, rpt.akreditasi
            ))
        except Exception as e:
            print("UPDATE status|akreditasi - GAGAL - {}".format(e))

#PTM_URL = 'https://pddikti.kemdikbud.go.id/perguruan-tinggi'
PTM_URL = 'https://pddikti.kemdiktisaintek.go.id/perguruan-tinggi'
MYDEBUG = True
PTMA_NAMA = 'Universitas Muhammadiyah Surakarta'

########################################################################################
## TAHAP-1 : 6 Maret 2025
## tabel ept_tpt sebagai REFERENSI item PTMA sumber data dari PP, manual ENTRY
##
########################################################################################

from ept.models import *

import sys

#Kumpulkan data per semester untuk semua PTMA
## =====================================
##  Semester GENAP 20252 belum muncul di Universitas, tetapi dalam daftar prodi sudah muncul
## =====================================

def go(START=0,STOP=1, SEMESTER=20252,TERBATAS=False,PTMA="PTMA",KODEPTMA="011003", PRODI="PRODI"):
    d = GetDriver()
    if  TERBATAS:
        dbPT = STpt.objects.filter(Q(kodept=KODEPTMA)).order_by('-organisasi','namapt')
    else:
        if PTMA!="PTMA":
            dbPT = STpt.objects.filter(Q(kodept=PTMA)).order_by('-organisasi','namapt')
        else:
            dbPT = STpt.objects.filter(~Q(kodept='umam24')).order_by('-organisasi','namapt')

    print('-----------------------------------------')
    print("TOTAL PTMA: {}".format(len(dbPT[START:STOP])))
    print('-----------------------------------------') 
    
    if len(dbPT)>0:
       for pt in dbPT[START:STOP]:
            print( "PTMA: {}-{}".format(pt.kodept,pt.namapt))  

            out = {}   #Temporary ptma

            if MYDEBUG: print("Buka link Perguruan Tinggi - https://pddikti.kemdiktisaintek.go.id/perguruan-tinggi")
            L = 'https://pddikti.kemdiktisaintek.go.id/perguruan-tinggi'
            
            d.get( L )

            
            rpt = STpt.objects.get(pk=pt.id)
            '''
            #spt = STpt.objects.filter(kodept=pt.kodept)
            if len(spt)>0:
                rpt = STpt.objects.get(pk=spt[0].id)
            else:
                rpt = STpt (
                    pt = json.dumps( out ),
                    kodept = pt.kodept,
                    namapt =  pt.namapt,
                    organisasi =  pt.organisasi,
                    jenis = pt.jenis
                )
            '''
            # rpt.save()
            print( "##############################" )
            print( "#### PTMA: id {} - {}".format(pt.id, pt.namapt))
            print( "##############################" )

            #d.implicitly_wait(30) # seconds
            if MYDEBUG: print("BukaCreate or Update Record pada tabel XTpt ")

            
            xp = '/html/body/div[1]/div/div[4]/div[6]/div/div[2]/div[1]/div[1]/div[1]/input'
            btnPATH = '/html/body/div[1]/div/div[4]/div[6]/div/div[2]/div[1]/div[1]/div[2]'            
            

            PTNAME = pt.namapt
            if pt.kodept=='023061':
                PTNAME = 'Sekolah Tinggi Keguruan dan Ilmu Pendidikan Muhammadiyah Pagaralam'
                
            PTMA_NAMA = pt.namapt
            INPUT_PTMA=False
            while not INPUT_PTMA:
                try:
                    print('get elemen input')
                    el = getElement(d,xp,60)

                    print('send_keys')
                    el.send_keys(PTNAME)

                    print('get elemen button search')
                    el = getElement(d,btnPATH,60)

                    print('click button search')
                    el.click()    
                    
                    if  pt.kodept in ['032023','121020','051013','141012']:
                        detailPATH = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[2]/div[2]/div[4]/div/button[1]'
                    else:
                        detailPATH = '//*[@id="root"]/div/div[4]/div[6]/div/div[2]/div[2]/div[1]/div[4]/div/button[1]'
                        
                    BTN_DETAIL = False
                    while not BTN_DETAIL:
                        try:
                            print('get elemen BUTTON detail')
                            rPT = getElement(d,detailPATH,20)

                            print('Click  BUTTON detail')
                            rPT.click()

                            BTN_DETAIL = True

                        except:
                            print('BTN detail belum muncul')
                            time.sleep(1)

                    PTM_URL = d.current_url
                    INPUT_PTMA=True

                except Exception as e:
                    print( "Nama PTM tidak ditemukan - {}".format(e))
                    continue
            
            
            out['namapt']      = PTNAME
            x = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[1]/p[2]',60)
            out['kode'] = x.text.strip()
            x = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[2]/p[2]',60)
            out['status'] = x.text.strip()

            out['akreditasi']  = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[3]/p[2]').text.strip()
            out['biayakuliah'] = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[4]/p[2]').text.strip()
            out['iddtlengkap'] = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[5]/p[2]').text.strip()
            out['tglberdiri']  = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[1]/div[5]/p[4]').text.strip()
            out['noskberdiri'] = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[1]/p[2]').text.strip()
            out['tglskberdiri']= d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[1]/p[4]').text.strip()

            out['telepon']     = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[2]/p[2]').text.strip()
            out['fax']         = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[2]/p[3]').text.strip()
            out['email']       = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[2]/p[4]').text.strip()
            out['website']     = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[2]/p[5]').text.strip()
            out['alamat']      = d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[4]/div/div/div[2]/div[3]/div/p').text.strip()
            
            #print("=============================")
            #print('## PT Profile ##')
            #print( out )
            #print("=============================")





            # start looking for data here
            pslinePATH='/html/body/div[1]/div/div[4]/div[5]/div/div[2]/div/div/select'            
            print("### Menunggu SELECT tampilkan SEMUA program studi muncul ###")

            SELECT_SEMUA_PRODI = False
            while not SELECT_SEMUA_PRODI:
                try:
                    x = getElement(d,pslinePATH,40)
                    select = Select(x)
                    select.select_by_visible_text("semua")
                    SELECT_SEMUA_PRODI = True
                except:
                    print("index pilihan semua prodi belum muncul")
                    time.sleep(1)
            
            SEMSelPATH ='/html/body/div[1]/div/div[4]/div[5]/div/div[2]/table/thead/tr[1]/th[6]/select'
            print("### Menunggu PILIHAN SEMESTER di tingkat UNIVERSTIAS muncul ###")
            
            SELECT_SEMESTER = False
            while not SELECT_SEMESTER:
                try:
                    x = getElement(d,SEMSelPATH,40)
                    select = Select(x)
                    time.sleep(2)
                    
                    # if SEMESTER==20252:
                    #    select.select_by_visible_text("Genap 2025")

                    ## Genap 2025 BELUM DIBUKA
                    select.select_by_visible_text("Ganjil 2025")

                    SELECT_SEMESTER = True
                    print("## SEMESTER #: {}".format(SEMESTER))

                except:
                    print("pilihan SEMESTER belum muncul")
                    time.sleep(1)

            
            



            rasio = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[6]/div[1]/div[1]/div[2]/div',60)
            #print( "Rasio Dosen mhs: {}".format(rasio.text.strip()))
            out['rasio_dm'] = rasio.text.strip()

            newmhs = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[6]/div[1]/div[2]/div[2]/div',60)
            #print( "Rerata mahasiswa baru: {}".format(newmhs.text.strip()))
            out['mhs_baru_rerata'] = newmhs.text.strip()

            lulus = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[6]/div[1]/div[3]/div[2]/div',60)
            #print( "Rerata lulus: {}".format(lulus.text.strip()))
            out['lulus_rerata'] = lulus.text.strip()

            #print( "Rerata Masa studi")
            table = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[6]/div[2]/div[2]/div/table/tbody',60)
            rows = table.find_elements(By.XPATH,'.//tr')
            if len(rows)>0:                
                mst = {}
                nr = 0
                for r in rows:
                    mst[ str(nr) ] = r.text.strip()
                    nr = nr + 1
            out['masa_studi_rerata'] = mst

            print("### PTMA Profile ###") 
            print( out )               
            # save profile pt to FTPT ##############
            print('########################################')
            print("### Save PROFILE PTMA - {} ###".format(PTMA_NAMA))
            rpt.pt = json.dumps( out )
            rpt.semester = SEMESTER
            try:
                rpt.save()
                print('########################################')
            except Exception as e:
                print("Gagal Simpan: {}".format(e))
                sys.exit()




            table = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[5]/div/div[2]/table',60)
            table = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[5]/div/div[2]/table/tbody',60)
            rows = table.find_elements(By.XPATH,'.//tr')
            if len(rows)>0:
                o = []
                for r in rows:
                    cs = r.find_elements(By.XPATH,'.//td')
                    if len(cs)>0:
                        n = 0
                        td = {}
                        for c in cs:
                            if n==0:
                                td['pskode'] = c.text  
                            elif n==1:
                                td['ps'] = c.text
                            elif n==2:
                                td['status'] = c.text
                            elif n==3:
                                td['jenjang'] = c.text
                            elif n==4:
                                td['akreditasi'] = c.text
                            elif n==5:
                                td['dsrasio'] = c.text
                            elif n==6:
                                td['nidn'] = c.text
                                td['tetap'] = c.text
                            elif n==7:
                                td['nidk'] = c.text
                                td['tidaktetap'] = c.text
                            elif n==8:
                                td['total'] = c.text
                            elif n==9:
                                td['mhs'] = c.text
                            elif n==10:
                                td['rasio'] = c.text

                            td['kodept'] = pt.kodept
                            td['namapt'] = pt.namapt
                            n = n +1
                        o.append(td)


                print("=============================")
                print('#### DAFTAR PROGRAM STUDI ####')
                print( o )
                print("=============================")

                # save daftar ps to FTPT ##############
                print("###################################")
                print("### Save ps.list | {} ###".format(PTMA_NAMA))
                x = {}
                KODEPT = pt.kodept
                x[KODEPT] = o
                rpt.ps = json.dumps( x )
                rpt.save()
                print("###################################")
                ########################################      


                ## GOTO INSIDE Program Studi                
                #print("UUUUUUUUUUUUU")
                #print("UUUUUUUUUUUUU")
                try:
                    ds = json.loads( rpt.ds )
                except Exception as e:
                    ds = rpt.ds    

                #print("UUUUUUUUUUUUU")                                        
                #print( ds[KODEPT] )

                if not (rpt.kodept in ds):                
                    ds[KODEPT] = {}
                
                #ms  = {}
                try:
                    ms = json.loads(rpt.ms)
                except:
                    ms = rpt.ms
                
                #print("UUUUUUUUUUUUU")
                #print(rpt.ms)

                if not (KODEPT in ms):
                    ms[KODEPT] = {}
                                

                #print( "DEBUG")    
                #print( ds ) 
                
                psjson = o
                
                nps = 0
                nrows = 12
                '''
                if ( KODEPT=='091036' ):
                    nps = 31                
                '''
                if ( KODEPT=='011014'):
                    nps = 0 
                if ( KODEPT=='091065'):
                    nps = 0 
                if ( KODEPT=='071060'):
                    nps = 46
                
                for ps in psjson[nps:]:
                  
                  #if not ps['pskode'] in ['20201','59201','60201','62201','63201','70201','74201',
                  #                        '84202','86208','88005','88201','88203']:
                  #    continue
                  
                  print("CCCCCCCCCCCCCCCCCCCCCCCCCC")
                  print( "{}-{}-{}".format(ps['pskode'],ps['jenjang'],ps['ps']) ) 
                  print("CCCCCCCCCCCCCCCCCCCCCCCCCC")

                  if 'Aktif' in ps['status']:
                    
                    try:
                        print('#')
                        print("## Read Detail PROGDI ###")
                        print('###')
                        print('######################################################')
                        print('## Prodi:  {}-{}|{} ###'.format(ps['jenjang'],ps['ps'], PTMA_NAMA))
                        print('######################################################')
                        print('##')
                        print('#')
                        
                        #print( ps )
                        NPS_CHECK = 1
                        PS_KODE = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[5]/div/div[2]/table/tbody/tr[' + str(NPS_CHECK) +']/td[1]').text.strip()

                        print( "DDDDDD:   {} vs {}".format(ps['pskode'],PS_KODE))

                        while ps['pskode']!=PS_KODE:
                            NPS_CHECK = NPS_CHECK + 1 
                            PS_KODE = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[5]/div/div[2]/table/tbody/tr[' + str(NPS_CHECK) +']/td[1]').text.strip()
                            
                        
                        print( "EEEEEE:   {} vs {}".format(ps['pskode'],PS_KODE))    

                        if PRODI!="PRODI":
                            if PS_KODE!=PRODI:
                                continue    #next program studi


                        ORIGINAL_WINDOW = d.current_window_handle

                        # Cick line PROGRAM STUDI
                        d.find_element(By.XPATH,'//*[@id="root"]/div/div[4]/div[5]/div/div[2]/table/tbody/tr[' + str(NPS_CHECK) +']/td[2]').click()

                        # nps = nps + 1
                        time.sleep(3)
                        x = getElementDisplay(d,'//*[@id="akreditasi"]/p[2]',60)
                        ps['akreditasi'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[1]/div[3]/div[1]/p[2]',60)
                        ps['dmrasio'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[1]/div[4]/div[1]/p[2]',60)
                        ps['skselenggara'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[1]/div[4]/div[2]/p[2]',60)
                        ps['tglsk'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="biaya-kuliah"]/p[2]',60)
                        ps['biayakuliah'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[1]/div[2]/div[2]/p[2]',60)
                        ps['akreditasi_inter'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="root"]/div/div[4]/div[4]/div/div[1]/div[3]/div[2]/p[2]',60)
                        ps['daftarterimarasio'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="tanggal-berdiri"]/p[2]',60)
                        ps['tglberdiri'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="phone"]',60)
                        ps['telepon'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="fax"]',60)
                        ps['fax'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="email"]/a',60)
                        ps['email'] = x.text.strip()
                        x = getElementDisplay(d,'//*[@id="web"]',60)
                        ps['website'] = x.text.strip()
                        
                        time.sleep(3)

                        
                        
                        ADA = False
                        while not ADA:
                            try:
                                x = getElement(d,'//*[@id="dosen_homebase"]',60)
                                select = Select(d.find_element(By.XPATH,'//*[@id="dosen_homebase"]'))
                                
                                '''
                                if SEMESTER==20241:
                                    select.select_by_visible_text("Gasal 2024")
                                if SEMESTER==20232:
                                    select.select_by_visible_text("Genap 2023")
                                if SEMESTER==20242:
                                    select.select_by_visible_text("Genap 2024")
                                if SEMESTER==20251:
                                    select.select_by_visible_text("Gasal 2025")
                                '''
                                select.select_by_visible_text("Genap 2025")

                                ADA = True
                            except:
                                print("semester belum muncul")
                                time.sleep(1)
                                pass

                        print("### Read DOSEN HOME BASE #######")
                        print('##### ps: {}-{} | {}'.format(ps['jenjang'],ps['ps'],PTMA_NAMA))
                        print('##')

                        try:
                            TABLE_AVAILABLE = False
                            while not TABLE_AVAILABLE:
                                try:
                                    x = getElementLengkap(d,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[1]/div[2]/div/div/p[2]',20)
                                    TABLE_AVAILABLE = True







                                except:
                                    print( "Table DOSEN HOME BASE BELUM AVAILABLE")
                                    time.sleep(1)


                            print( "Halaman: {}".format(x.text) )
                            MAX_PAGE = int( x.text.strip() )
                            if MAX_PAGE>0:
                                o = []
                                n=1
                                while n < (MAX_PAGE +1):
                                    table = d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[1]/div[1]/table/tbody')
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['no'] = c.text.strip()
                                                        elif nc==1:
                                                            dsn['nama'] = c.text.strip()
                                                        elif nc==2:
                                                            dsn['nidn'] = c.text.strip()
                                                        elif nc==3:
                                                            dsn['nuptk'] = c.text.strip()
                                                        elif nc==4:
                                                            dsn['pendidikan'] = c.text.strip()
                                                        elif nc==5:
                                                            dsn['status'] = c.text.strip()
                                                        elif nc==6:
                                                            dsn['ikatankerja'] = c.text.strip()
                                                        nc = nc+1    
                                                    o.append( dsn )
                                                    # ds['homebase'].append( dsn )

                                    n = n+1

                                    
                                    d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[1]/div[2]/div/button[2]').click()
                                    time.sleep(1)
                                
                                print( "DAFTAR DOSEN - HOME BASE")
                                print( o )
                                print( "===============================" )

                                
                                

                                # save daftar ps to FTPT ##############
                                print("#############################################")
                                print("### Save DOSEN HOMEBASE list json on STpt ###")
                                print("#############################################")
                                
                                
                                KODEPS = ps['pskode']
                                ds[pt.kodept][KODEPS] = {}
                                ds[pt.kodept][KODEPS]['homebase'] = o                                                                                                
                                rpt.ds = json.dumps( ds )
                                rpt.save()
                                ########################################      





                        except Exception as e:
                            print("Error - Tidak ada data Dosen  HOMEBASE - {}".format(e))
                            pass


                        print("### Read DOSEN RASIO #######")
                        print('##### ps: {}-{}|{}'.format(ps['jenjang'],ps['ps'],PTMA_NAMA))
                        print('##')            

                        if PRODI!="PRODI":
                                 continue

                        try:
                            #go to tab Dosen Penghitung Rasio
                            print("### Menunggu TAB DOSEN PENGHITUNG RASIO muncul ###")
                            print("## Link PT: {}".format(PTM_URL))
                            #while x is None:
                            x = getElement(d,'/html/body/div[1]/div/div[4]/div[7]/div/div/nav/ul/li[2]',90)
                            #x = d.find_element(By.XPATH,'/html/body/div[1]/div/div[4]/div[7]/div/div/nav/ul/li[2]')
                            x.click()
                            
                            time.sleep(5)
                            
                            # SEMESTER = 20251
                            
                            print("# Select semester dosen home base # {}".format(SEMESTER))
                            time.sleep(5)
                            
                            
                            
                            
                            ADA = False
                            while not ADA:
                                try:
                                    x = getElement(d,'//*[@id="dosen_rasio"]',60)
                                    select = Select(d.find_element(By.XPATH,'//*[@id="dosen_rasio"]'))                                    
                                    
                                    '''
                                    if SEMESTER==20241:
                                        select.select_by_visible_text("Gasal 2024")
                                    if SEMESTER==20232:
                                        select.select_by_visible_text("Genap 2023")
                                    if SEMESTER==20242:
                                        select.select_by_visible_text("Genap 2024")
                                    if SEMESTER==20251:
                                        select.select_by_visible_text("Gasal 2025")
                                    '''

                                    select.select_by_visible_text("Genap 2025")

                                    ADA = True
                                except:
                                    print("index semester belum muncul")
                                    time.sleep(1)
                                    pass


                            #time.sleep(3)
                            TABLE_AVAILABLE = False
                            while not TABLE_AVAILABLE:
                                try:
                                    x = getElementLengkap(d,'/html/body/div[1]/div/div[4]/div[7]/div/div/div[2]/div[2]/div[2]/div/div/p[2]',20)
                                    TABLE_AVAILABLE = True
                                except:
                                    print( "Table DOSEN RASIO BELUM AVAILABLE")
                                    time.sleep(1)
                            

                            print( "Halaman: {}".format(x.text) )
                            MAX_PAGE = int( x.text.strip() )
                            if MAX_PAGE>0:
                                o = []
                                n=1
                                while n < (MAX_PAGE +1):
                                    
                                    x     = getElementLengkap(d,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[2]/div[1]/table/tbody',60)
                                    table = d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[2]/div[1]/table/tbody')
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:
                                            dsn = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    dsn = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            dsn['no'] = c.text.strip()
                                                        elif nc==1:
                                                            dsn['nama'] = c.text.strip()
                                                        elif nc==2:
                                                            dsn['nidn'] = c.text.strip()
                                                        elif nc==3:
                                                            dsn['nuptk'] = c.text.strip()
                                                        elif nc==4:
                                                            dsn['pendidikan'] = c.text.strip()
                                                        elif nc==5:
                                                            dsn['status'] = c.text.strip()
                                                        elif nc==6:
                                                            dsn['ikatankerja'] = c.text.strip()
                                                        nc = nc+1    
                                                    o.append( dsn )
                                                    #ds['rasio'].append( dsn )
                                    n = n+1

                                    
                                    d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[2]/div[2]/div/button[2]').click()
                                    time.sleep(1)
                                
                                print( "DAFTAR DOSEN - PENGHITUNG RASIO")
                                print( o )
                                print( "===============================" )

                                # save daftar ps to STPT ##############
                                print("#############################################")
                                print("### Save DOSEN PEMBAGI RASIO json on STpt ###")
                                print("#############################################")
                                KODEPS = ps['pskode']
                                # ds[KODEPS] = {}
                                ds[pt.kodept][KODEPS]['rasio'] = o
                                rpt.ds = json.dumps( ds )
                                rpt.save()
                                ########################################      




                        except Exception as e:
                            print("Error - Tidak ada data Dosen PENGHITUNG RASIO  - {}".format(e))
                            pass


                        print("### Read MAHASISWA/SEMESTER #######")
                        print('##### ps: {}-{}'.format(ps['jenjang'],ps['ps']))
                        print('##')                   

                        try:
                            #go to tab Mahasiswa/semeser
                            print("### Menunggu TAB DAFTAR MAHASISWA/SEMESTER muncul ###")
                            print("## Link PT: {}".format(PTM_URL))

                            
                            TABLE_AVAILABLE = False
                            while not TABLE_AVAILABLE:
                                try:
                                    x = getElement(d,'/html/body/div[1]/div/div[4]/div[7]/div/div/nav/ul/li[3]',40)
                                    x.click()
                                    time.sleep(3)
                                    x = getElementLengkap(d,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[3]/div[2]/div/div/p[2]',60)
                                    x = d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[3]/div[2]/div/div/p[2]')
                                    TABLE_AVAILABLE = True
                                except:
                                    print( "Table MAHASISWA SEMESTER BELUM AVAILABLE")
                                    time.sleep(1)



                            print( "Halaman: {}".format(x.text) )
                            MAX_PAGE = int( x.text.strip() )
                            if MAX_PAGE>3:
                                MAX_PAGE = 3   #Genap 2017/2018 (last semester)

                            if MAX_PAGE>0:
                                o = []
                                n=1
                                while n < (MAX_PAGE +1):
                                    x     = getElementLengkap(d,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[3]/div[1]/table/tbody',60)
                                    table = d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[3]/div[1]/table/tbody')
                                    if not (table is None):
                                        rows = table.find_elements(By.XPATH,'.//tr')
                                        if len(rows)>0:
                                            mhs = {}
                                            for r in rows:
                                                cs = r.find_elements(By.XPATH,'.//td')
                                                if len(cs)>0:
                                                    nc = 0
                                                    mhs = {}
                                                    for c in cs:
                                                        if nc==0:
                                                            mhs['semester'] = c.text.strip()
                                                        elif nc==1:
                                                            mhs['mahasiswa'] = c.text.strip()                                                        
                                                        nc = nc+1    
                                                    o.append( mhs )
                                    n = n+1

                                    
                                    d.find_element(By.XPATH,'//*[@id="tabs-riwayat-dosen"]/div[2]/div[3]/div[2]/div/button[2]').click()
                                    time.sleep(1)
                                
                                print( "DAFTAR MAHASISWA/SEMESTER")
                                print( o )
                                print( "===============================" )

                                # save daftar ps to FTPT ##############
                                print("########################################")
                                print("### Save MAHASISWA LIST json on STpt_ms ###")
                                print("########################################")
                                
                                KODEPS = ps['pskode']
                                ms[pt.kodept][KODEPS] = {}                                
                                ms[pt.kodept][KODEPS]['mahasiswa'] = o
                                rpt.ms = json.dumps( ms )
                                rpt.save()
                                ########################################   

                        except Exception as e:
                            print("Error - Tidak ada Mahasiswa - {}".format(e))
                            pass



                        # 3 item berikut data masih loading
                        x = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[5]/div/div[1]/p',60)
                        ps['infoumum'] = x.text.strip()
                        x = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[5]/div/div[2]/p',60)
                        ps['belajarilmu'] = x.text.strip()
                        x = getElementLengkap(d,'//*[@id="root"]/div/div[4]/div[5]/div/div[3]/div',60)
                        ps['kompetensi'] = x.text.strip()

                        print('#################################################')
                        print('Detail PROGRAM STUDI')
                        print('##### ps: {}-{}'.format(ps['jenjang'],ps['ps']))
                        print('##')
                        print( ps )

                        # save daftar ps to FTPT ##############
                        print("### Save profile ps on ITpt - JUNI 2025 ###")
                        KODEPS = ps['pskode']
                        #if ds[pt.kodept] is None:ds[pt.kodept][KODEPS] 
                        #    ds[pt.kodept] = {}
                        #ds[pt.kodept][KODEPS] = {}

                        try:
                            if not isinstance(ds,dict):
                                ds = {}
                        except Exception as e:
                            ds = {}
                            pass

                        if not pt.kodept in ds:
                            ds[pt.kodept] = {}
                        if not KODEPS in ds[pt.kodept]:
                            ds[pt.kodept][KODEPS] = {}
                            
                        ds[pt.kodept][KODEPS]['profile'] = ps
                        rpt.ds = json.dumps( ds )
                        rpt.save()
                        ########################################                            
                        
                    except Exception as e:
                       print( "Ada kesalahan - {}".format(e))
                       pass


                    # start dari awal lagi
                    # time.sleep(3)
                    # Go BACK to Previous page
                    print("############################")
                    print("## Open PTM main page, intent to the next PRODI ######")
                    print("############################")
                    # d.execute_script("window.history.go(-1)")
                    d.get(PTM_URL)
                    time.sleep(5)
                    
                    #Tampilkan semua prodi
                    print("####################################")
                    print("## Select SEMESTER: {} ######".format(SEMESTER))
                    print("####################################")
                    SEMSelPATH ='//*[@id="root"]/div/div[4]/div[5]/div/div[2]/table/thead/tr[1]/th[6]/select'
                    print("### Menunggu PILIHAN SEMESTER di tingkat UNIVERSTIAS muncul ###")
                    
                    SELECT_SEMESTER  = False
                    while not SELECT_SEMESTER:
                        try:
                            x = getElement(d,SEMSelPATH,20)
                            select = Select(x)
                            time.sleep(2)
                            
                            select.select_by_visible_text("Ganjil 2025")
                            # select.select_by_visible_text("Genap 2025")   # belum dibuka
                            
                            '''
                            SEMESTER = 20251
                            if SEMESTER==20232:
                                select.select_by_visible_text("Genap 2023")
                            if SEMESTER==20241:
                                select.select_by_visible_text("Gasal 2024")                           
                            if SEMESTER==20242:
                                select.select_by_visible_text("Genap 2024")
                            if SEMESTER==20251:
                                select.select_by_visible_text("Ganjil 2025")
                            if SEMESTER==20252:
                                select.select_by_visible_text("Genap 2025")
                            '''

                            SELECT_SEMESTER = True
                        except:
                            print( 'pilihan SEMESTER belum muncul')
                            time.sleep(1)

                    
                    

                    print("############################")
                    print("## Tampilkan SEMUA PROGRAM STUDI ######")
                    print("############################")
                    #pslinePATH='//*[@id="root"]/div/div[4]/div[5]/div/div[2]/div/div/select'
                    pslinePATH='/html/body/div[1]/div/div[4]/div[5]/div/div[2]/div/div/select'
                    print("### Menunggu PILIHAN tampilkan daftar SEMUA Program Studi muncul ###")

                    SELECT_SEMUA_PRODI = False
                    while not SELECT_SEMUA_PRODI:
                        try:
                            x = getElement(d,pslinePATH,60)
                            time.sleep(2)
                            select = Select(x)
                            select.select_by_visible_text("semua")
                            SELECT_SEMUA_PRODI = True
                        except:
                            print('pilihan SEMUA PRODI belum muncul')            
                            time.sleep(1)
                    

                ## Read JUmlah MAHASISWA / semester

            time.sleep(2)
         # else:
         #    print("PTMA - {} - sudah di proses go next PTMA".format( pt.kodept )) 
    time.sleep(3)
  
def unidn(STOP=1):
    rs = GTdd.objects.filter(nidn="-").values('kodept','kodeps').annotate(count=Count('kodeps')).order_by('kodept','kodeps')
    print ( "ROWS number #: {}".format(len(rs)) )
    #STOP = len(rs)
    if len(rs)>0:
        for r in rs[0:STOP]:
            print( "{}|{}|{}".format(r['kodept'], r['kodeps'], r['count']) )
            go(r['kodept'], r['kodeps'])
            #update_ds_satu(0,r['count'])

            
            
## SYNCH with FORLAP

from forlap.models import Tpt as forlapTpt, Tptm, Tptmref, Tps, Tprodi, Tmahasiswa, Tdosen


from django.db.models import Sum, Count

def synctoforlap_tpt(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = FTpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PT = json.loads( rpt.pt )
        except:
            PT = rpt.pt

        ## check forlap_tpt
        rows = forlapTpt.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tpt = forlapTpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tpt = forlapTpt()
            action = "INSERT"

            rforlap_tpt.kode = rpt.kodept
            rforlap_tpt.namapt = rpt.namapt
            rforlap_tpt.namapt_banpt = rpt.namapt
        
        rforlap_tpt.linkpt = "https://pddikti.kemdikbud.go.id/perguruan-tinggi"
        rforlap_tpt.status = PT['status']
        rforlap_tpt.peringkat = PT['akreditasi']

        rforlap_tpt.berdiri = PT['tglberdiri']
        rforlap_tpt.nomorsk = PT['noskberdiri']
        rforlap_tpt.tanggalsk = PT['tglskberdiri']

        rforlap_tpt.telepon = PT['telepon']
        rforlap_tpt.faximile = PT['fax']
        rforlap_tpt.email = PT['email']
        rforlap_tpt.website = PT['website']
        rforlap_tpt.alamat = PT['alamat']

        #hitung jumlah dosen
        dsn = FTps.objects.filter(kodept=rpt.kodept).aggregate( Sum('total',default=0) )
        rforlap_tpt.dosen = dsn['total__sum']
        rforlap_tpt.dosen_pre = dsn['total__sum']
        #hitung jumlah mahasiswa 
        mhs = FTps.objects.filter(kodept=rpt.kodept).aggregate( Sum('mahasiswa',default=0) )
        rforlap_tpt.mahasiswa = mhs['mahasiswa__sum']
        rforlap_tpt.mahasiswa_pre = mhs['mahasiswa__sum']

        rforlap_tpt.rasio = PT['rasio_dm']
        rforlap_tpt.rasio_pre = PT['rasio_dm']

        try:
            rforlap_tpt.save()
            print("{} forlap_tpt - SUKSES - {}|{}".format(action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{} forlap_tpt - GAGAL - {}".format(action,e))

def synctoforlap_tptm(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = FTpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PT = json.loads( rpt.pt )
        except:
            PT = rpt.pt

        ## check forlap_tpt
        rows = Tptm.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tptm = Tptm.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tptm = Tptm()
            action = "INSERT"

        rforlap_tptm.kode = rpt.kodept
        rforlap_tptm.nama = rpt.namapt
        rforlap_tptm.nama_pp = rpt.namapt
        rforlap_tptm.jenis = str(rpt.jenis).upper()

        rforlap_tptm.aisyiyah = 1
        if "Muhammadiyah" in rpt.organisasi:
            rforlap_tptm.aisyiyah = 0
        
        rforlap_tptm.status = 0
        if 'Aktif' in rpt.status:
            rforlap_tptm.status = 1
        
        rows = forlapTpt.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            rTpt = forlapTpt.objects.get(pk=rows[0]['id'])
            rforlap_tptm.Tpt = rTpt                

        try:
            rforlap_tptm.save()
            print("{} forlap_tptm - SUKSES - {}|{}".format(action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{} forlap_tptm - GAGAL - {}".format(action,e))

def synctoforlap_tptmref(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = FTpt.objects.get(pk=kpt['id'])
            #KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PT = json.loads( rpt.pt )
        except:
            PT = rpt.pt

        ## check forlap_tpt
        rows = Tptmref.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tptmref = Tptmref.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tptmref = Tptmref()
            action = "INSERT"

        rforlap_tptmref.kode = rpt.kodept
        rforlap_tptmref.ptma = rpt.namapt
        rforlap_tptmref.jenis = rpt.jenis
        rforlap_tptmref.organisasi = rpt.organisasi
        
        rows = forlapTpt.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            rTpt = forlapTpt.objects.get(pk=rows[0]['id'])
            rforlap_tptmref.Tpt = rTpt                

        try:
            rforlap_tptmref.save()
            print("{} forlap_tptmref - SUKSES - {}|{}".format(action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{} forlap_tptmref - GAGAL - {}".format(action,e))

def synctoforlap_tps(START=0,STOP=1):
    n=1
    rps = FTps.objects.all().values('kodeps','namaps','jenjang').annotate(NPS=Count('kodeps')).order_by('namaps')
    for ps in rps[START:STOP]:
        ## check forlap_tpt
        rows = Tps.objects.values('id').filter(kode=ps['kodeps'],jenjang=ps['jenjang'])
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tps = Tps.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tps = Tps()
            action = "INSERT"

        rforlap_tps.kode = ps['kodeps']
        rforlap_tps.namaprodi = ps['namaps']
        rforlap_tps.jenjang = ps['jenjang']
        rforlap_tps.namalain = str( ps['NPS'] )

        
        try:
            rforlap_tps.save()
            print("{:5} # {} forlap_tps - SUKSES - {}|{}|{}".format(n,action, ps['jenjang'],ps['kodeps'], ps['namaps']))
        except Exception as e:
            print("{:5} # {} forlap_tps - GAGAL - {}".format(n,action,e))
        
        n = n+1

def synctoforlap_tprodi(START=0,STOP=1):
    dbPS = FTps.objects.values('id','kodept','kodeps').filter(semester=20241).order_by('kodept', 'kodeps')
    N = 1
    for kps in dbPS[START:STOP]:
        try:
            rps = FTps.objects.get(pk=kps['id'])
            KODEPT = rps.kodept

        except Exception as e:
            print('Program Studi tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            PS = json.loads( rps.ps )
        except:
            PS = rps.ps

        ## check forlap_tpt
        rows = Tprodi.objects.values('id').filter(kodept=rps.kodept,kode=rps.kodeps)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tprodi = Tprodi.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tprodi = Tprodi()
            action = "INSERT"

        rforlap_tprodi.kodept = rps.kodept
        rforlap_tprodi.kode = rps.kodeps
        rforlap_tprodi.namaprodi = rps.namaps
        
        rforlap_tprodi.linkprodi = "https://pddikti.kemdikbud.go.id/program-studi"
        rforlap_tprodi.status = rps.status
        rforlap_tprodi.jenjang = rps.jenjang
        rforlap_tprodi.peringkat = rps.akreditasi
        rforlap_tprodi.dosen = rps.total
        rforlap_tprodi.mahasiswa = rps.mahasiswa
        rforlap_tprodi.dosen2 = rps.total
        rforlap_tprodi.mahasiswa2 = rps.mahasiswa
        rforlap_tprodi.rasio = rps.rasio
        rforlap_tprodi.rasio2 = rps.rasio

        rforlap_tprodi.berdiri = PS['tglberdiri'] 
        rforlap_tprodi.nomorsk = PS['skselenggara']
        rforlap_tprodi.tanggalsk = PS['tglsk']
        rforlap_tprodi.telepon = PS['telepon']
        rforlap_tprodi.faximile = PS['fax']
        rforlap_tprodi.email = PS['email']
        rforlap_tprodi.website = PS['website']
        rforlap_tprodi.expired = "no"
        #rforlap_tprodi.alamat = PS['alamat']

        rows = FTdd.objects.filter(kodept=rps.kodept,kodeps=rps.kodeps,pendidikan='S3').annotate(doktor=Count('pendidikan'))    
        if len(rows)>0:
            rforlap_tprodi.doktor = rows[0].doktor

        rows = FTdd.objects.filter(kodept=rps.kodept,kodeps=rps.kodeps,fungsional='Profesor').annotate(prof=Count('fungsional'))    
        if len(rows)>0:
            rforlap_tprodi.profesor = rows[0].prof

        ## get Tps
        rows = Tps.objects.values('id').filter(kode=rps.kodeps,jenjang=rps.jenjang)
        if len(rows)>0:
            rForlap_tps = Tps.objects.get(pk=rows[0]['id'])
            rforlap_tprodi.Tps = rForlap_tps
        else:
            rforlap_tprodi.Tps = 0

        rows = forlapTpt.objects.values('id').filter(kode=rps.kodept)
        if len(rows)>0:
            rForlap_tpt = forlapTpt.objects.get(pk=rows[0]['id'])
            rforlap_tprodi.Tpt = rForlap_tpt
        else:
            rforlap_tprodi.Tpt = 0

        rows = Tptmref.objects.values('id').filter(kode=rps.kodept)
        if len(rows)>0:
            rForlap_tptmref = Tptmref.objects.get(pk=rows[0]['id'])
            rforlap_tprodi.Tptmref = rForlap_tptmref
        else:
            rforlap_tprodi.Tptmref = 0
        
        try:
            rforlap_tprodi.save()
            print("{:4}|{} forlap_tprodi - SUKSES - {}|{}|{}|{}".format(N, action, rps.kodept,rps.jenjang,rps.kodeps,rps.namaps))
        except Exception as e:
            print("{:4}{} forlap_tprodi - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoforlap_tms(START=0,STOP=1):
    dbMHS = FTms.objects.values('id',).filter(tahun__gte=2024).order_by('kodept', 'kodeps')
    print("Total RECORD # {:7}".format(len(dbMHS)))
    N = 1
    for kmhs in dbMHS[START:STOP]:
        try:
            rmhs = FTms.objects.get(pk=kmhs['id'])
            KODEPT = rmhs.kodept

        except Exception as e:
            print('Jumlah mahasiswa/semester tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        ## check forlap_tpt
        SEM  = rmhs.semester[10:] + ' ' + rmhs.semester[:4]
        # print(SEM)
        rows = Tmahasiswa.objects.values('id').filter(kodept=rmhs.kodept,kodeprodi=rmhs.kodeps,semester=SEM)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tmahasiswa = Tmahasiswa.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tmahasiswa = Tmahasiswa()
            action = "INSERT"

        rforlap_tmahasiswa.kodept = rmhs.kodept
        rforlap_tmahasiswa.kodeprodi = rmhs.kodeps
        rforlap_tmahasiswa.jenjang = rmhs.jenjang
        rforlap_tmahasiswa.tahun = rmhs.tahun
        rforlap_tmahasiswa.jumlah = rmhs.jumlah
        rforlap_tmahasiswa.semester = SEM

        ## get Tps
        rows = Tprodi.objects.values('id').filter(kode=rmhs.kodeps,kodept=rmhs.kodept)
        if len(rows)>0:
            rForlap_tprodi = Tprodi.objects.get(pk=rows[0]['id'])
            rforlap_tmahasiswa.Tprodi = rForlap_tprodi
        else:
            pass #rforlap_tmahasiswa.Tprodi = 0

        rows = forlapTpt.objects.values('id').filter(kode=rmhs.kodept)
        if len(rows)>0:
            rForlap_tpt = forlapTpt.objects.get(pk=rows[0]['id'])
            rforlap_tmahasiswa.Tpt = rForlap_tpt
        else:
            pass #rforlap_tmahasiswa.Tpt = 0

        try:
            rforlap_tmahasiswa.save()
            print("{:4}|{} forlap_tmahasiswa - SUKSES - {}|{}|{}|{}".format(N, action, rmhs.kodept,rmhs.jenjang,rmhs.kodeps,rmhs.semester))
        except Exception as e:
            print("{:4}|{} forlap_tmahasiswa - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoforlap_tdosen(START=0,STOP=1):
    dbPS = HTdd.objects.values('id').filter(S20241=1).order_by('kodept', 'kodeps')
    N = START
    for kds in dbPS[START:STOP]:
        try:
            rds = HTdd.objects.get(pk=kds['id'])
            KODEPT = rds.kodept

        except Exception as e:
            print('Data DOSEN tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        
        ## check forlap_tpt
        rows = Tdosen.objects.values('id').filter(
            kodept=rds.kodept,kodeprodi=rds.kodeps, nama=rds.nama,pendidikan=rds.pendidikan, 
            jabfung=rds.fungsional)
        if len(rows)>0:
            # print( "ADA ")
            rforlap_tdosen = Tdosen.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rforlap_tdosen = Tdosen()
            action = "INSERT"

        rforlap_tdosen.kodept = rds.kodept
        rforlap_tdosen.kodeprodi = rds.kodeps
        rforlap_tdosen.nama = rds.nama
        rforlap_tdosen.pendidikan = rds.pendidikan
        rforlap_tdosen.idreg = rds.nidn
        rforlap_tdosen.gelar = rds.gelar
        
        rforlap_tdosen.linkdosen  = "https://pddikti.kemdikbud.go.id/"
        rforlap_tdosen.gender = rds.jk
        if not rds.jk in ['L','P']:
            rforlap_tdosen.gender = 'L'

        rforlap_tdosen.jabfung = rds.fungsional
        rforlap_tdosen.statuskerja = rds.ikatankerja
        rforlap_tdosen.statusaktif = rds.statuskeaktifan

        ## get Tps
        rows = Tprodi.objects.values('id').filter(kode=rds.kodeps,kodept=rds.kodept)
        if len(rows)>0:
            rForlap_tprodi = Tprodi.objects.get(pk=rows[0]['id'])
            rforlap_tdosen.Tprodi = rForlap_tprodi
        
        rows = forlapTpt.objects.values('id').filter(kode=rds.kodept)
        if len(rows)>0:
            rForlap_tpt = forlapTpt.objects.get(pk=rows[0]['id'])
            rforlap_tdosen.Tpt = rForlap_tpt
        
        rows = Tptmref.objects.values('id').filter(kode=rds.kodept)
        if len(rows)>0:
            rForlap_tptmref = Tptmref.objects.get(pk=rows[0]['id'])
            rforlap_tdosen.Tptmref = rForlap_tptmref
        
        try:
            rforlap_tdosen.save()
            print("{:4}|{} forlap_tdosen - SUKSES - {}|{}|{}|{}|{}|{}".format(N, action, rds.nidn, rds.kodept,rds.kodeps,rds.nama, rds.pendidikan, rds.fungsional))
        except Exception as e:
            print("{:4}{} forlap_tdosen - GAGAL - {}".format(N, action,e))

        N = N+1

## SYNCH with JPT
from jpt.models import Tpt as jTpt, Tpsd as jTpsd, Tpsr as jTpsr, Tps as jTps, Tds as jTds
def synctoJPT_tpt(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = FTpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms



        ## check jpt_tpt
        rows = jTpt.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rjpt_tpt = jTpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rjpt_tpt = jTpt()
            action = "INSERT"

        rjpt_tpt.kodept = rpt.kodept
        rjpt_tpt.namapt = rpt.namapt
        rjpt_tpt.jenis =  rpt.jenis
        rjpt_tpt.organisasi = rpt.organisasi

        rjpt_tpt.pt = rpt.pt
        rjpt_tpt.ps = rpt.ps
        rjpt_tpt.ds = rpt.ds
        rjpt_tpt.ms = rpt.ms
        rjpt_tpt.idsp = "-"
                
        try:
            rjpt_tpt.save()
            print("{} jpt_tpt - SUKSES - {}|{}".format(action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{} jpt_tpt - GAGAL - {}".format(action,e))

def synctoJPT_tps(START=0,STOP=1):
    dbPS = FTps.objects.all().values('id').order_by('kodept', 'kodeps')
    N = 1
    for kps in dbPS[START:STOP]:
        rps = FTps.objects.get(pk=kps['id'])

        try:
            jPS = json.loads( rps.ps )
        except:
            jPS = rps.ps

        ## check jpt_tpt
        rows = jTps.objects.values('id').filter(kodept=rps.kodept, kodeps=rps.kodeps)
        if len(rows)>0:
            rjpt_tps = jTps.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rjpt_tps = jTps()
            action = "INSERT"

        rjpt_tps.kodept = rps.kodept
        rjpt_tps.kodeps = rps.kodeps
        rjpt_tps.namaps = rps.namaps
        rjpt_tps.semester = rps.semester
        rjpt_tps.sts =  rps.sts
        rjpt_tps.idsms =  "-" 
        rjpt_tps.ps = rps.ps

        rows = jTpt.objects.values('id').filter(kodept=rps.kodept)
        if len(rows)>0:
            rjTpt = jTpt.objects.get(pk=rows[0]['id'])
            rjpt_tps.Tpt = rjTpt 

        try:
            rjpt_tps.save()
            print("{:5} # {} jpt_tps - SUKSES - {}|{}|{}|{}".format(N, action, rps.semester, rps.kodept, rps.kodeps, rps.namaps))
        except Exception as e:
            print("{:5} # {} jpt_tps - GAGAL - {}".format(N, action,e))

        N = N + 1

def synctoJPT_tds(START=0,STOP=1):
    dbDS = FTdd.objects.values('id').filter(S20232=1).order_by('id')
    N = START
    for kds in dbDS[START:STOP]:
        rds = FTdd.objects.get(pk=kds['id'])


        ## check jpt_tpt
        rows = jTds.objects.values('id').filter(
                kodept=rds.kodept, kodeps=rds.kodeps, 
                namads=rds.nama, pendidikan=rds.pendidikan
            )
        if len(rows)>0:
            rjpt_tds = jTds.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rjpt_tds = jTds()
            action = "INSERT"

        rjpt_tds.kodept = rds.kodept
        rjpt_tds.kodeps = rds.kodeps
        rjpt_tds.namads = rds.nama
        rjpt_tds.pendidikan = rds.pendidikan
        rjpt_tds.idreg = rds.fungsional
        rjpt_tds.ds = rds.sekolah
        
        rows = jTpt.objects.values('id').filter(kodept=rds.kodept)
        if len(rows)>0:
            rjTpt = jTpt.objects.get(pk=rows[0]['id'])
            rjpt_tds.Tpt = rjTpt
        rows = jTps.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps)
        if len(rows)>0:
            rjTps = jTps.objects.get(pk=rows[0]['id'])
            rjpt_tds.Tps = rjTps

        rows = Tdosen.objects.values('id').filter(
            kodept=rds.kodept, kodeprodi=rds.kodeps,
            nama = rds.nama, pendidikan=rds.pendidikan
            )
        if len(rows)>0:
            rTdosen = Tdosen.objects.get(pk=rows[0]['id'])
            rjpt_tds.Tds = rTdosen
         

        try:
            rjpt_tds.save()
            print("{:5} # {} jpt_tds - SUKSES - {}|{}|{}|{}|{}".format(
                    N, action, rds.kodept, rds.kodeps, rds.nama, 
                    rds.pendidikan, rds.fungsional)
                )
        except Exception as e:
            print("{:5} # {} jpt_tds - GAGAL - {}".format(N, action,e))

        N = N + 1

## TAHAP-2  Sinkronisasi dengan TABEL FPT dan HPT
from ept.models import Tpt as eTpt, Tps as eTps, Tdd as eTdd, Tds as eTds
## Sync with ept
def synctoEPT_tpt(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = FTpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows = eTpt.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rept_tpt = eTpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tpt = eTpt()
            action = "INSERT"

        rept_tpt.kodept = rpt.kodept
        rept_tpt.namapt = rpt.namapt
        rept_tpt.jenis =  rpt.jenis
        rept_tpt.organisasi = rpt.organisasi

        rept_tpt.pt = rpt.pt
        rept_tpt.ps = rpt.ps
        rept_tpt.ds = rpt.ds
        rept_tpt.ms = rpt.ms
        rept_tpt.idsp = "-"
        rept_tpt.semester = 20241

                
        try:
            rept_tpt.save()
            print("{:4}|{} ept_tpt - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} ept_tpt - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoEPT_tps(START=0,STOP=1):
    dbPS = FTps.objects.all().values('id').order_by('kodept', 'kodeps')
    N = START
    for kps in dbPS[START:STOP]:
        rps = FTps.objects.get(pk=kps['id'])

        try:
            jPS = json.loads( rps.ps )
        except:
            jPS = rps.ps

        ## check jpt_tpt
        rows = eTps.objects.values('id').filter(kodept=rps.kodept, kodeps=rps.kodeps)
        if len(rows)>0:
            rept_tps = eTps.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tps = eTps()
            action = "INSERT"

        rept_tps.kodept = rps.kodept
        rept_tps.kodeps = rps.kodeps
        rept_tps.namaps = rps.namaps
        rept_tps.semester = rps.semester
        rept_tps.sts =  rps.sts
        rept_tps.idsms =  "-" 
        rept_tps.ps = rps.ps
        rept_tps.status = rps.status

        rows = eTpt.objects.values('id').filter(kodept=rps.kodept)
        if len(rows)>0:
            reTpt = eTpt.objects.get(pk=rows[0]['id'])
            rept_tps.Tpt = reTpt 

        try:
            rept_tps.save()
            print("{:5} # {} ept_tps - SUKSES - {}|{}|{}".format(N, action, rps.kodept, rps.kodeps, rps.namaps))
        except Exception as e:
            print("{:5} # {} ept_tps - GAGAL - {}".format(N, action,e))

        N = N + 1

def synctoEPT_tdd(START=0,STOP=1):
    
    #Carefull with SEMESTER
    dbDS = FTdd.objects.values('id').filter(S20251=1).order_by('id')
    
    print("ROWS number #: {}".format(len(dbDS)))
    N = START
    for kds in dbDS[START:STOP]:
        rds = FTdd.objects.get(pk=kds['id'])


        ## check jpt_tpt
        rows = eTdd.objects.values('id').filter(
                kodept=rds.kodept, kodeps=rds.kodeps, 
                nama=rds.nama, pendidikan=rds.pendidikan                
            )
        if len(rows)>0:
            rept_tdd = eTdd.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tdd = eTdd()
            action = "INSERT"

        rept_tdd.kodept = rds.kodept
        rept_tdd.kodeps = rds.kodeps
        rept_tdd.nama = rds.nama
        rept_tdd.pendidikan = rds.pendidikan
        rept_tdd.sekolah = rds.sekolah
        rept_tdd.fungsional = rds.fungsional
        rept_tdd.ikatankerja = rds.ikatankerja
        rept_tdd.statuskeaktifan = rds.statuskeaktifan
        rept_tdd.namaprodi = rds.namaps
        rept_tdd.pt = rds.namapt
        rept_tdd.jk = rds.jk
        rept_tdd.pendidikan = rds.pendidikan
        rept_tdd.nidn = rds.nidn
        rept_tdd.gelar = rds.gelar


        
        rept_tdd.S20241 = 1
        
        rows = eTpt.objects.values('id').filter(kodept=rds.kodept)
        if len(rows)>0:
            reTpt = eTpt.objects.get(pk=rows[0]['id'])
            rept_tdd.Tpt = reTpt
        rows = eTps.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps, semester='20241' )
        if len(rows)>0:
            reTps = eTps.objects.get(pk=rows[0]['id'])
            rept_tdd.Tps = reTps
         

        try:
            rept_tdd.save()
            print("{:5} # {} ept_tdd - SUKSES - {}|{}|{}|{}|{}".format(
                    N, action, rds.kodept, rds.kodeps, rds.nama, 
                    rds.pendidikan, rds.fungsional)
                )
        except Exception as e:
            print("{:5} # {} ept_tdd - GAGAL - {}".format(N, action,e))

        N = N + 1

########################################################
# TAHAP 2: SYNC from HTpt to FTpt
#####################################################


def sHTpt2FTpt(START=0,STOP=1):
    dbPT = HTpt.objects.filter(Q(kodept='051022')|Q(kodept='091004')|Q(kodept='061004')|Q(kodept='101018')|
                                  Q(kodept='071024')|Q(kodept='161018')|Q(kodept='021004')|Q(kodept='051007')|                                  
                                  Q(kodept='081010')).values('id','kodept').order_by('-organisasi','namapt')
    #dbPT = HTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = HTpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows =  FTpt.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rept_tpt = FTpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tpt = eTpt()
            action = "INSERT"

        rept_tpt.kodept = rpt.kodept
        rept_tpt.namapt = rpt.namapt
        rept_tpt.jenis =  rpt.jenis
        rept_tpt.organisasi = rpt.organisasi

        rept_tpt.pt = rpt.pt
        rept_tpt.ps = rpt.ps
        rept_tpt.ds = rpt.ds
        rept_tpt.ms = rpt.ms
        rept_tpt.idsp = "-"
        #rept_tpt.semester = 20241
        rept_tpt.semester = rpt.semester

                
        try:
            rept_tpt.save()
            print("{:4}|{} HTpt to FTpt - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} HTpt to FTpt - GAGAL - {}".format(N, action,e))

        N = N+1

def sHTps2FTps(START=0,STOP=1):
    dbPS = HTps.objects.all().values('id').order_by('kodept', 'kodeps')
    #dbPS = HTps.objects.filter(Q(kodept='051022')|Q(kodept='091004')|Q(kodept='061004')|Q(kodept='101018')|
    #                              Q(kodept='071024')|Q(kodept='161018')|Q(kodept='021004')|Q(kodept='051007')|                                  
    #                              Q(kodept='081010')).values('id').order_by('kodept','kodeps')
    N = START
    for kps in dbPS[START:STOP]:
        rps = HTps.objects.get(pk=kps['id'])

        try:
            jPS = json.loads( rps.ps )
        except:
            jPS = rps.ps

        ## check ept_FTpt
        o = {}
        rows = FTps.objects.values('id').filter(kodept=rps.kodept, kodeps=rps.kodeps)
        if len(rows)>0:
            rept_tps = FTps.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tps = FTps()
            action = "INSERT"
        o['action'] = action

        rept_tps.kodept = rps.kodept
        o['kodept'] = rps.kodept
        rept_tps.kodeps = rps.kodeps
        o['kodeps'] = rps.kodeps
        rept_tps.namaps = rps.namaps
        o['namaps'] = rps.namaps 
        rept_tps.semester = rps.semester
        o['semester'] = rps.semester
        rept_tps.sts =  rps.sts
        o['sts'] =  rps.sts
        rept_tps.idsms =  "-" 
        rept_tps.ps = rps.ps
        rept_tps.status = rps.status
        o['status'] = rps.status

        rept_tps.jenjang = rps.jenjang
        o['jenjang'] = rps.jenjang
        rept_tps.akreditasi = rps.akreditasi
        o['akreditasi'] = rps.akreditasi
        rept_tps.akreditasi_internasional = rps.akreditasi_internasional
        o['akreditasi_internasional'] = rps.akreditasi_internasional
        rept_tps.dosen_rasio = rps.dosen_rasio
        o['dosen_rasio'] = rps.dosen_rasio
        rept_tps.dosen_homebase = rps.dosen_homebase
        o['dosen_homebase'] = rps.dosen_homebase
        rept_tps.nidk = rps.nidk
        o['nidk'] = rps.nidk
        rept_tps.nidn = rps.nidn
        o['nidn'] = rps.nidn
        rept_tps.total = rps.total
        o['total'] = rps.total
        rept_tps.mahasiswa = rps.mahasiswa
        o['mahasiswa'] = rps.mahasiswa
        rept_tps.rasio = rps.rasio
        o['rasio']= rps.rasio

        rows = FTpt.objects.values('id').filter(kodept=rps.kodept)
        if len(rows)>0:
            reTpt = FTpt.objects.get(pk=rows[0]['id'])
            rept_tps.Tpt = reTpt 
            o['FTpt'] = reTpt 

        try:
            rept_tps.save()
            print("{:5} # {} HTps_to_Ftps - SUKSES - {}|{}|{}".format(N, action, rps.kodept, rps.kodeps, rps.namaps))
            print( o )
            print( "######################################################" )
            print(" ")
        except Exception as e:
            print("{:5} # {} HTps_to_Ftps - GAGAL - {}".format(N, action,e))

        N = N + 1

def sFTpt2FTms(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    for kpt in dbPT[START:STOP]:
        try:
            rpt = FTpt.objects.get(pk=kpt['id'])
            KODEPT = rpt.kodept

        except Exception as e:
            print('PTMA tidak ditemukan - {}'.format(e))
            continue  # next PTMA

        try:
            MHS = json.loads( rpt.ms )
        except:
            MHS = rpt.ms
        
        if KODEPT in MHS:
            for KODEPS in MHS[KODEPT]:
                rows = FTps.objects.values('id').filter(
                    kodept=KODEPT, kodeps=KODEPS
                )
                if len(rows)>0:
                    rps = FTps.objects.get(pk=rows[0]['id'])

                for mhs in MHS[KODEPT][KODEPS]['mahasiswa']:
                    rows = FTms.objects.values('id').filter(
                        kodept=KODEPT,kodeps=KODEPS,semester=mhs['semester']
                    )
                    if len(rows)>0:
                        rmhs = FTms.objects.get(pk=rows[0]['id'])
                        action = 'UPDATE'
                    else:
                        rmhs = FTms()
                        action = 'SIMPAN'
                    rmhs.kodept = KODEPT
                    rmhs.kodeps = KODEPS
                    rmhs.semester = mhs['semester']
                    rmhs.jumlah = int( mhs['mahasiswa'] )
                    rmhs.tahun = int( str(mhs['semester'])[0:4] )
                    rmhs.jenjang = rps.jenjang
                    rmhs.Tpt = rpt
                    rmhs.Tps = rps

                    try:
                        rmhs.save()
                        print("{} data mahasiswa/semester - SUKSES - {}|{}|{}:{}".format(
                            action, rmhs.kodept, rmhs.kodeps, rmhs.semester, rmhs.jumlah
                        ))
                    except Exception as e:
                        print("Simpan/update data mahasiswa/semester - GAGAL - {}".format(e))


def sHTdd2FTdd(START=0,STOP=1):
    #SEMESTER 20241 (GASAL)
    #dbDS = HTdd.objects.values('id').filter(Q(kodept='051022')|Q(kodept='091004')|Q(kodept='061004')|Q(kodept='101018')|
    #                              Q(kodept='071024')|Q(kodept='161018')|Q(kodept='021004')|Q(kodept='051007')|                                  
    #                              Q(kodept='081010'), S20241=1
    #                                        ).order_by('id')
    dbDS = HTdd.objects.values('id').order_by('id')
    print("MAX DOSEN: {}".format(len(dbDS)))
    N = START
    for kds in dbDS[START:STOP]:
        rds = HTdd.objects.get(pk=kds['id'])


        ## check jpt_tpt
        rows = FTdd.objects.values('id').filter(
                kodept=rds.kodept, kodeps=rds.kodeps, 
                nama=rds.nama, pendidikan=rds.pendidikan
            )
        if len(rows)>0:
            rept_tdd = FTdd.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tdd = FTdd()
            action = "INSERT"

        rept_tdd.kodept = rds.kodept
        rept_tdd.kodeps = rds.kodeps
        rept_tdd.nama = rds.nama
        rept_tdd.pendidikan = rds.pendidikan
        rept_tdd.sekolah = rds.sekolah
        rept_tdd.fungsional = rds.fungsional
        rept_tdd.ikatankerja = rds.ikatankerja
        rept_tdd.statuskeaktifan = rds.statuskeaktifan
        rept_tdd.namaps = rds.namaps
        rept_tdd.namapt = rds.namapt
        rept_tdd.jk = rds.jk
        rept_tdd.pendidikan = rds.pendidikan
        rept_tdd.nidn = rds.nidn
        rept_tdd.gelar = rds.gelar
        rept_tdd.S20241 = 1
        
        rows = FTpt.objects.values('id').filter(kodept=rds.kodept)
        if len(rows)>0:
            reTpt = FTpt.objects.get(pk=rows[0]['id'])
            rept_tdd.Tpt = reTpt
        #rows = FTps.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps, semester='20241' ) #only Current semester
        rows = FTps.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps)  #All Semester
        if len(rows)>0:
            reTps = FTps.objects.get(pk=rows[0]['id'])
            rept_tdd.Tps = reTps
         

        try:
            rept_tdd.save()
            print("{:5} # {} ept_HTdd_to_Ftdd - SUKSES - {}|{}|NIDN:{}|{}|{}|{}".format(
                    N, action, rds.kodept, rds.kodeps, rds.nidn,rds.nama, 
                    rds.pendidikan, rds.fungsional)
                )
        except Exception as e:
            print("{:5} # {} ept_HTdd_to_Ftdd - GAGAL - {}".format(N, action,e))

        N = N + 1


from pdd.models import Tpt as pTpt, Tpt2022, Tps2022, Tds2022, Tms2022, Tptma
## Sync with pdd
def synctoPDD_tpt(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = FTpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows = pTpt.objects.values('id').filter(kode=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rpdd_tpt = pTpt.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rpdd_tpt = pTpt()
            action = "INSERT"

        rpdd_tpt.kode = rpt.kodept
        rpdd_tpt.namapt = rpt.namapt
        rpdd_tpt.linkpt = 'https://pddikti.kemdikbud.go.id/'
        rpdd_tpt.status =  rpt.status
        rpdd_tpt.peringkat = rpt.akreditasi

        rpdd_tpt.berdiri = jPT['tglberdiri']
        rpdd_tpt.nomorsk = jPT['noskberdiri']
        rpdd_tpt.tanggalsk = jPT['tglskberdiri']
        rpdd_tpt.telepon = jPT['telepon']
        rpdd_tpt.faximile = jPT['fax']
        rpdd_tpt.email = jPT['email']
        rpdd_tpt.website = jPT['website']
        rpdd_tpt.alamat = jPT['alamat']

        r = FTps.objects.filter(kodept=rpt.kodept).aggregate(dosen=Sum('total'), mhs=Sum('mahasiswa'))
        rpdd_tpt.dosen = r['dosen']
        rpdd_tpt.mahasiswa = r['mhs']
        rpdd_tpt.rasio = jPT['rasio_dm']
        rpdd_tpt.dosen_pre = r['dosen']
        rpdd_tpt.mahasiswa_pre = r['mhs']
        rpdd_tpt.rasio_pre = jPT['rasio_dm']
                
        try:
            rpdd_tpt.save()
            print("{:4}|{} pdd_tpt - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} pdd_tpt - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoPDD_tpt2022(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = FTpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows = Tpt2022.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rpdd_tpt = Tpt2022.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rpdd_tpt = Tpt2022()
            action = "INSERT"

        rpdd_tpt.kode = rpt.kodept
        rpdd_tpt.namapt = rpt.namapt
        rpdd_tpt.linkpt = 'https://pddikti.kemdikbud.go.id/'
        rpdd_tpt.statuspt =  rpt.status
        rpdd_tpt.akreditasi = rpt.akreditasi

        rpdd_tpt.berdiritgl = jPT['tglberdiri']
        rpdd_tpt.nomorsk = jPT['noskberdiri']
        rpdd_tpt.tanggalsk = jPT['tglskberdiri']
        rpdd_tpt.alamat = jPT['alamat']

        rpdd_tpt.telepon = jPT['telepon']
        rpdd_tpt.faximile = jPT['fax']
        rpdd_tpt.email = jPT['email']
        rpdd_tpt.organisasi = rpt.organisasi
        rpdd_tpt.jenis = rpt.jenis
        
        try:
            rpdd_tpt.save()
            print("{:4}|{} pdd_tpt2022 - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} pdd_tpt2022 - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoPDD_tps2022(START=0,STOP=1):
    dbPS = FTps.objects.all().values('id').order_by('kodept', 'kodeps')
    N = START
    for kps in dbPS[START:STOP]:
        rps = FTps.objects.get(pk=kps['id'])

        try:
            jPS = json.loads( rps.ps )
        except:
            jPS = rps.ps

        ## check jpt_tpt
        rows = Tps2022.objects.values('id').filter(kodept=rps.kodept, kodeps=rps.kodeps)
        if len(rows)>0:
            rept_tps = Tps2022.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tps = Tps2022()
            action = "INSERT"

        rept_tps.kodept = rps.kodept
        rept_tps.kodeps = rps.kodeps
        rept_tps.namaprodi = rps.namaps
        rept_tps.status =  rps.status
        rept_tps.jenjang =  rps.jenjang 
        rept_tps.akreditasi =  rps.akreditasi
        rept_tps.berdiri = jPS['tglberdiri']
        rept_tps.nomorsk = jPS['skselenggara']
        rept_tps.tanggalsk = jPS['tglsk']
        rept_tps.telepon = jPS['telepon']
        rept_tps.faximile = jPS['fax']
        rept_tps.email = jPS['email']
        rept_tps.website = jPS['website']

        rept_tps.dosenrasio = rps.dosen_rasio
        rept_tps.dosenhbnidn = rps.nidn
        rept_tps.dosenhbnidk = rps.nidk
        rept_tps.mahasiswa = rps.mahasiswa
        rept_tps.rasio =  rps.rasio
        rept_tps.kompetensi = jPS['kompetensi']

        
        rows = Tpt2022.objects.values('id').filter(kodept=rps.kodept)
        if len(rows)>0:
            reTpt = Tpt2022.objects.get(pk=rows[0]['id'])
            rept_tps.Tpt = reTpt 

        try:
            rept_tps.save()
            print("{:5} # {} pdd_tps2022 - SUKSES - {}|{}|{}".format(N, action, rps.kodept, rps.kodeps, rps.namaps))
        except Exception as e:
            print("{:5} # {} pdd_tps2022 - GAGAL - {}".format(N, action,e))

        N = N + 1

def synctoPDD_tms2022(START=0,STOP=1):
    dbMHS = FTms.objects.values('id',).filter(tahun__gte=2024).order_by('id')
    print("Total RECORD # {:7}".format(len(dbMHS)))
    N = START
    for kmhs in dbMHS[START:STOP]:
        rmhs = FTms.objects.get(pk=kmhs['id'])

        ## check forlap_tpt
        SEM  = rmhs.semester[10:] + ' ' + rmhs.semester[:4]
        # print(SEM)
        rows = Tms2022.objects.values('id').filter(kodept=rmhs.kodept,kodeprodi=rmhs.kodeps,semester=SEM)
        if len(rows)>0:
            # print( "ADA ")
            rpdd_tms2022 = Tms2022.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rpdd_tms2022 = Tms2022()
            action = "INSERT"

        rpdd_tms2022.kodept = rmhs.kodept
        rpdd_tms2022.kodeprodi = rmhs.kodeps
        rpdd_tms2022.semester = SEM
        rpdd_tms2022.jumlah = rmhs.jumlah
        rpdd_tms2022.jenjang = rmhs.jenjang
        rpdd_tms2022.tahun = rmhs.tahun
        
        ## get Tps
        rows = Tps2022.objects.values('id').filter(kodeps=rmhs.kodeps,kodept=rmhs.kodept)
        if len(rows)>0:
            rpdd_tps2022 = Tps2022.objects.get(pk=rows[0]['id'])
            rpdd_tms2022.Tprodi = rpdd_tps2022
        else:
            pass #rforlap_tmahasiswa.Tprodi = 0

        rows = Tpt2022.objects.values('id').filter(kodept=rmhs.kodept)
        if len(rows)>0:
            rpdd_tps2022 = Tpt2022.objects.get(pk=rows[0]['id'])
            rpdd_tms2022.Tpt = rpdd_tps2022
        else:
            pass #rforlap_tmahasiswa.Tpt = 0

        try:
            rpdd_tms2022.save()
            print("{:4}|{} pdd_tms2022 - SUKSES - {}|{}|{}|{}".format(N, action, rmhs.kodept,rmhs.jenjang,rmhs.kodeps,rmhs.semester))
        except Exception as e:
            print("{:4}|{} pdd_tms2022 - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoPDD_tptma(START=0,STOP=1):
    dbPT = FTpt.objects.all().values('id','kodept').order_by('-organisasi', 'namapt')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = FTpt.objects.get(pk=kpt['id'])
        
        try:
            jPT = json.loads( rpt.pt )
        except:
            jPT = rpt.pt

        try:
            jPS = json.loads( rpt.ps )
        except:
            jPS = rpt.ps

        try:
            jDS = json.loads( rpt.ds )
        except:
            jDS = rpt.ds

        try:
            jMS = json.loads( rpt.ms )
        except:
            jMS = rpt.ms


        ## check jpt_tpt
        rows = Tptma.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            # print( "ADA ")
            rpdd_tpt = Tptma.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rpdd_tpt = Tptma()
            action = "INSERT"

        rpdd_tpt.kodept = rpt.kodept
        rpdd_tpt.namapt = rpt.namapt
        rpdd_tpt.linkpt = 'https://pddikti.kemdikbud.go.id/'
        rpdd_tpt.organisasi = rpt.organisasi
        rpdd_tpt.jenis = rpt.jenis

        rows = Tpt2022.objects.values('id').filter(kodept=rpt.kodept)
        if len(rows)>0:
            rpdd_tpt2022 = Tpt2022.objects.get(pk=rows[0]['id'])
            rpdd_tpt.Tpt2022 = rpdd_tpt2022
        
        try:
            rpdd_tpt.save()
            print("{:4}|{} pdd_tpt2022 - SUKSES - {}|{}".format(N, action, rpt.kodept, rpt.namapt))
        except Exception as e:
            print("{:4}|{} pdd_tpt2022 - GAGAL - {}".format(N, action,e))

        N = N+1

def synctoPDD_tds2022(START=0,STOP=1):
    #SEMESTER 20241 (GASAL)
    #dbDS = HTdd.objects.values('id').filter(Q(kodept='051022')|Q(kodept='091004')|Q(kodept='061004')|Q(kodept='101018')|
    #                              Q(kodept='071024')|Q(kodept='161018')|Q(kodept='021004')|Q(kodept='051007')|                                  
    #                              Q(kodept='081010'), S20241=1
    #                                        ).order_by('id')
    dbDS = HTdd.objects.values('id').order_by('id')
    print("MAX DOSEN: {}".format(len(dbDS)))
    N = START
    for kds in dbDS[START:STOP]:
        rds = HTdd.objects.get(pk=kds['id'])


        ## check jpt_tpt
        rows = Tds2022.objects.values('id').filter(
                kodept=rds.kodept, kodeprodi=rds.kodeps, 
                nama=rds.nama, pendidikan=rds.pendidikan
            )
        if len(rows)>0:
            rept_tdd = Tds2022.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        else:
            rept_tdd = Tds2022()
            action = "INSERT"

        rept_tdd.kodept = rds.kodept
        rept_tdd.kodeprodi = rds.kodeps
        rept_tdd.nama = rds.nama
        rept_tdd.pendidikan = rds.pendidikan
        #rept_tdd.sekolah = rds.sekolah
        rept_tdd.jabfung = rds.fungsional
        rept_tdd.statuskerja = rds.ikatankerja
        rept_tdd.statusaktif = rds.statuskeaktifan
        #rept_tdd.namaps = rds.namaps
        #rept_tdd.namapt = rds.namapt
        rept_tdd.gender = rds.jk
        rept_tdd.nidn = rds.nidn
        rept_tdd.gelar = rds.gelar
        #rept_tdd.S20241 = 1
        
        rows = Tpt2022.objects.values('id').filter(kodept=rds.kodept)
        if len(rows)>0:
            reTpt = Tpt2022.objects.get(pk=rows[0]['id'])
            rept_tdd.Tpt = reTpt
        #rows = FTps.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps, semester='20241' ) #only Current semester
        rows = Tps2022.objects.values('id').filter(kodept=rds.kodept, kodeps=rds.kodeps)  #All Semester
        if len(rows)>0:
            reTps = Tps2022.objects.get(pk=rows[0]['id'])
            rept_tdd.Tps = reTps
         

        try:
            rept_tdd.save()
            print("{:5} # {} ept_HTdd_to_PDD_Tds - SUKSES - {}|{}|NIDN:{}|{}|{}|{}".format(
                    N, action, rds.kodept, rds.kodeps, rds.nidn,rds.nama, 
                    rds.pendidikan, rds.fungsional)
                )
        except Exception as e:
            print("{:5} # {} ept_HTdd_to_PDD_Tds - GAGAL - {}".format(N, action,e))

        N = N + 1






from st3.models import Aff

#Sync with SYNTA (ST3)
def SintaToPDD_tpt2022(START=0,STOP=1):
    dbPT = Aff.objects.all().values('id').order_by('id')
    N = START
    for kpt in dbPT[START:STOP]:
        rpt = Aff.objects.get(pk=kpt['id'])

        ## check jpt_tpt
        rows = Tpt2022.objects.values('id').filter(kodept=rpt.kode_pt)
        if len(rows)>0:
            # print( "ADA ")
            rpdd_tpt = Tpt2022.objects.get(pk=rows[0]['id'])
            action = "UPDATE"
        
            rpdd_tpt.id_aff = rpt.id_aff
            
            try:
                rpdd_tpt.save()
                print("{:4}|{} ID_AFF - pdd_tpt2022 - SUKSES - {}|{}".format(N, action, rpt.kode_pt, rpt.afiliasi_name))
            except Exception as e:
                print("{:4}|{} ID_AFF - pdd_tpt2022 - GAGAL - {}".format(N, action,e))

        N = N+1

#from PDD_Tptma
def syncToST3_AFF(START=0,STOP=1):
    dPTs = Tptma.objects.filter(idsinta__gt=0).values('id','kodept').order_by('-organisasi', 'namapt')

    print("New ENTRY: {}".format( len(dPTs)))
    N = START
    for kpt in dPTs[START:STOP]:
        rpt = Tptma.objects.get(pk=kpt['id'])

        rs=Aff.objects.filter(kode_pt=rpt.kodept)
        if len(rs)<1:
            r = Aff()
            r.kode_pt = rpt.kodept
            r.id_aff = rpt.idsinta
            r.afiliasi_name = rpt.namapt
            r.save()
            print("Simpan PTMA masuk ke SINTA baru: {}|{}|{}".format(
                r.kode_pt,r.afiliasi_name,r.id_aff
            ))





