
"""
QArt — QR Photo Art ST - v6 Final
- Title changed
- Load photo moved right below URL
- RESET/Reload buttons nearby
- Reduced vertical spacing in left panel/sidebar
- Full controls: Local/Otsu/Halftone + cutoff + save PNG
- Green frame correctly mapped (full box) + square lesser-side

Deploy: rename to app.py for Streamlit Cloud or keep name and set main file path
Run locally: streamlit run app.py
pip install streamlit streamlit-cropper opencv-python numpy "qrcode[pil]" pillow
"""

import cv2, numpy as np, qrcode
from qrcode import base as qr_base
import streamlit as st
from PIL import Image

try:
    import zxingcpp
except Exception:
    zxingcpp = None
try:
    from streamlit_cropper import st_cropper
    HAS_CROPPER = True
except Exception:
    HAS_CROPPER = False

def _build_gf():
    exp = np.zeros(512, np.uint8); log = np.zeros(256, np.int32); x=1
    for i in range(255):
        exp[i]=x; log[x]=i; x<<=1
        if x & 0x100: x ^= 0x11D
    exp[255:510]=exp[0:255]
    mul=np.zeros((256,256),np.uint8); a=np.arange(1,256)
    mul[1:,1:]=exp[log[a][:,None]+log[a][None,:]]
    return exp,mul
GF_EXP,GF_MUL=_build_gf()
def rs_divisor(n):
    g=[1]
    for i in range(n):
        a=int(GF_EXP[i]); new=g+[0]
        for j,c in enumerate(g): new[j+1]^=int(GF_MUL[c,a])
        g=new
    return np.array(g[1:],np.uint8)
def rs_remainders(div,kmax):
    n=len(div); R=np.zeros((kmax,n),np.uint8); r=div.copy()
    for m in range(kmax): R[m]=r; lead=r[0]; r=np.concatenate([r[1:],np.zeros(1,np.uint8)]) ^ GF_MUL[lead][div]
    return R
ECC_INFO={"L":(qrcode.constants.ERROR_CORRECT_L,1),"M":(qrcode.constants.ERROR_CORRECT_M,0),"Q":(qrcode.constants.ERROR_CORRECT_Q,3),"H":(qrcode.constants.ERROR_CORRECT_H,2)}
def _format_bits(ecl_bits,mask):
    data=(ecl_bits<<3)|mask; rem=data
    for _ in range(10): rem=(rem<<1)^((rem>>9)*0x537)
    return ((data<<10)|rem)^0x5412
def mask_matrix(mask,ys,xs):
    x,y=xs,ys
    if mask==0: m=(x+y)%2==0
    elif mask==1: m=y%2==0
    elif mask==2: m=x%3==0
    elif mask==3: m=(x+y)%3==0
    elif mask==4: m=(x//3+y//2)%2==0
    elif mask==5: m=(x*y%2+x*y%3)==0
    elif mask==6: m=(x*y%2+x*y%3)%2==0
    else: m=((x+y)%2+x*y%3)%2==0
    return m.astype(np.uint8)
class Layout:
    def __init__(self,ver):
        self.ver=ver; n=self.size=4*ver+17
        isf=self.isf=np.zeros((n,n),bool); base=self.base=np.zeros((n,n),np.uint8)
        def setf(x,y,v):
            if 0<=x<n and 0<=y<n: isf[y,x]=True; base[y,x]=1 if v else 0
        for i in range(n): setf(6,i,i%2==0); setf(i,6,i%2==0)
        for cx,cy in ((3,3),(n-4,3),(3,n-4)):
            for dy in range(-4,5):
                for dx in range(-4,5): setf(cx+dx,cy+dy,max(abs(dx),abs(dy)) not in (2,4))
        if ver>1:
            na=ver//7+2; step=26 if ver==32 else (ver*4+na*2+1)//(na*2-2)*2
            pos=[6]+[n-7-(na-2-i)*step for i in range(na-1)]
            for i in range(na):
                for j in range(na):
                    if (i,j) in ((0,0),(0,na-1),(na-1,0)): continue
                    for dy in range(-2,3):
                        for dx in range(-2,3): setf(pos[i]+dx,pos[j]+dy,max(abs(dx),abs(dy))!=1)
        if ver>=7:
            rem=ver
            for _ in range(12): rem=(rem<<1)^((rem>>11)*0x1F25)
            bits=(ver<<12)|rem
            for i in range(18): b=(bits>>i)&1; a,c=n-11+i%3,i//3; setf(a,c,b); setf(c,a,b)
        self._fmt_pos=self._format_positions(n)
        for x,y,_ in self._fmt_pos: setf(x,y,0)
        setf(8,n-8,1)
        ys,xs=[],[]
        for right in range(n-1,0,-2):
            if right<=6: right-=1
            for vert in range(n):
                for j in range(2):
                    x=right-j; y=(n-1-vert) if ((right+1)&2)==0 else vert
                    if not isf[y,x]: ys.append(y); xs.append(x)
        self.ys=np.array(ys,np.int32); self.xs=np.array(xs,np.int32)
    @staticmethod
    def _format_positions(n):
        p=[]
        for i in range(0,6): p.append((8,i,i))
        p+=[(8,7,6),(8,8,7),(7,8,8)]
        for i in range(9,15): p.append((14-i,8,i))
        for i in range(0,8): p.append((n-1-i,8,i))
        for i in range(8,15): p.append((8,n-15+i,i))
        return p
    def with_format(self,ecl_bits,mask):
        m=self.base.copy(); fb=_format_bits(ecl_bits,mask)
        for x,y,i in self._fmt_pos: m[y,x]=(fb>>i)&1
        return m
_layout_cache={}
def get_layout(ver):
    if ver not in _layout_cache: _layout_cache[ver]=Layout(ver)
    return _layout_cache[ver]
class Plan:
    def __init__(self,ver,ecl):
        self.ver,self.ecl=ver,ecl; self.layout=get_layout(ver)
        blocks=qr_base.rs_blocks(ver,ECC_INFO[ecl][0])
        self.nb=len(blocks); self.data_lens=[b.data_count for b in blocks]
        self.ecc_len=blocks[0].total_count-blocks[0].data_count
        self.n_data=sum(self.data_lens); self.T=self.n_data+self.nb*self.ecc_len; self.R=self.T*8
        self.starts=np.concatenate([[0],np.cumsum(self.data_lens)[:-1]]).astype(int)
        self.div=rs_divisor(self.ecc_len); self.Rtab=rs_remainders(self.div,max(self.data_lens))
        sb,sd=[],[]
        for i in range(max(self.data_lens)):
            for b,k in enumerate(self.data_lens):
                if i<k: sb.append(b); sd.append(self.starts[b]+i)
        for e in range(self.ecc_len):
            for b in range(self.nb): sb.append(b); sd.append(-1)
        self.stream_block=np.array(sb); self.stream_data=np.array(sd)
        self.data_to_stream=np.zeros(self.n_data,int)
        for t in range(self.n_data): self.data_to_stream[self.stream_data[t]]=t
        self.block_cw=[np.flatnonzero(self.stream_block==b) for b in range(self.nb)]
        ys,xs=self.layout.ys[:self.R],self.layout.xs[:self.R]
        self.maskbits=np.stack([mask_matrix(s,ys,xs) for s in range(8)],axis=1)
        self._A_cache={}
    def ecc_for(self,D):
        out=np.zeros((self.nb,self.ecc_len),np.uint8)
        for b in range(self.nb):
            k=self.data_lens[b]; d=D[self.starts[b]:self.starts[b]+k]
            rows=self.Rtab[k-1-np.arange(k)]
            out[b]=np.bitwise_xor.reduce(GF_MUL[d[:,None],rows],axis=0)
        return out
    def stream_from(self,D):
        ecc=self.ecc_for(D); s=np.zeros(self.T,np.uint8)
        s[:self.n_data]=D[self.stream_data[:self.n_data]]; s[self.n_data:]=ecc.T.reshape(-1)
        return s
    def get_A(self,n_fixed):
        if n_fixed in self._A_cache: return self._A_cache[n_fixed]
        n_free=self.n_data-n_fixed; nv=n_free*8
        A=np.zeros((self.R,nv),np.uint8)
        for g in range(n_fixed,self.n_data):
            t=self.data_to_stream[g]
            for q in range(8): A[t*8+q,(g-n_fixed)*8+q]=1
        q8=np.arange(8)
        for b in range(self.nb):
            k=self.data_lens[b]; lo=max(self.starts[b],n_fixed); hi=self.starts[b]+k
            if lo>=hi: continue
            gs=np.arange(lo,hi); E=self.Rtab[k-1-(gs-self.starts[b])]
            rows=((self.n_data+np.arange(self.ecc_len)*self.nb+b)[:,None]*8+q8[None,:])
            for q in range(8):
                contrib=GF_MUL[E,1<<(7-q)]; bits=np.unpackbits(contrib[...,None],axis=-1)
                A[rows[None,:,:],((gs-n_fixed)*8+q)[:,None,None]]=bits
        W=(nv+8+63)//64; pad=np.zeros((self.R,W*64),np.uint8); pad[:,:nv]=A
        Apack=np.packbits(pad,axis=1,bitorder="little").view(np.uint64)
        res=(A,Apack,A.any(axis=1)); self._A_cache={n_fixed:res}; return res
_plan_cache={}
def get_plan(ver,ecl):
    if (ver,ecl) not in _plan_cache: _plan_cache[(ver,ecl)]=Plan(ver,ecl)
    return _plan_cache[(ver,ecl)]
def fixed_stream(data,ver):
    cc=8 if ver<10 else 16
    bits="0100"+format(len(data),f"0{cc}b")+"".join(format(b,"08b") for b in data)+"0000"
    bits+="0"*(-len(bits)%8)
    return np.array([int(bits[i:i+8],2) for i in range(0,len(bits),8)],np.uint8)
def min_version_for(data,ecl,start):
    for v in range(start,41):
        try:
            if len(data)>=(1<<(8 if v<10 else 16)): continue
            n_fixed=len(fixed_stream(data,v))
        except ValueError: continue
        p=get_plan(v,ecl)
        if n_fixed<=p.n_data: return v
    raise ValueError("Data too large")
def eliminate(M,order,n):
    W=M.shape[1]; basis=np.zeros((n,W),np.uint64); is_piv=np.zeros(n,bool)
    for r in order:
        row=M[r].copy()
        bits=np.unpackbits(row.view(np.uint8),bitorder="little")[:n].astype(bool)
        sel=np.flatnonzero(bits&is_piv)
        if sel.size: row^=np.bitwise_xor.reduce(basis[sel],axis=0); bits=np.unpackbits(row.view(np.uint8),bitorder="little")[:n].astype(bool)
        nz=np.flatnonzero(bits)
        if nz.size==0: continue
        p=int(nz[0]); col=(basis[:,p>>6]>>np.uint64(p&63))&np.uint64(1); idx=np.flatnonzero(col)
        if idx.size: basis[idx]^=row
        basis[p]=row; is_piv[p]=True
    return basis,is_piv
def qart_solve(plan,payload,target,weight,budget_frac=0.4):
    L=plan.layout; R=plan.R; ys,xs=L.ys[:R],L.xs[:R]
    fixed=fixed_stream(payload,plan.ver); n_fixed=len(fixed)
    D=np.zeros(plan.n_data,np.uint8); D[:n_fixed]=fixed
    c=np.unpackbits(plan.stream_from(D)).astype(np.uint8)
    tgt=target[ys,xs].astype(np.uint8); w=weight[ys,xs].astype(np.float64)
    nv=(plan.n_data-n_fixed)*8
    if nv>0:
        A,Apack,Aany=plan.get_A(n_fixed)
        rhs=(tgt[:,None]^c[:,None]^plan.maskbits).astype(np.uint64)
        M=Apack.copy()
        for s in range(8): cs=nv+s; M[:,cs>>6]|=rhs[:,s]<<np.uint64(cs&63)
        cand=np.flatnonzero(Aany); order=cand[np.argsort(-w[cand],kind="stable")]
        basis,is_piv=eliminate(M,order,nv)
        X=np.zeros((nv,8),np.float32)
        for s in range(8): cs=nv+s; X[:,s]=((basis[:,cs>>6]>>np.uint64(cs&63))&np.uint64(1)).astype(np.float32)
        cw=np.zeros((R,8),np.uint8)
        for i in range(0,R,512):
            blk=A[i:i+512].astype(np.float32)@X
            cw[i:i+512]=(blk.astype(np.int64)&1).astype(np.uint8)
        cw^=c[:,None]
    else:
        cw=np.repeat(c[:,None],8,axis=1); is_piv=np.zeros(0,bool)
    final_all=cw^plan.maskbits
    cost=(w[:,None]*(final_all!=tgt[:,None])).sum(axis=0)
    mask=int(np.argmin(cost)); final=final_all[:,mask].copy()
    mism=(final!=tgt)&(w>0)
    t_per_block=plan.ecc_len//2; bud=int(t_per_block*max(0.0,min(1.0,budget_frac)))
    if bud>0 and mism.any():
        gain=np.bincount(np.arange(R)//8,weights=w*mism,minlength=plan.T)
        flip_cw=np.zeros(plan.T,bool)
        for b in range(plan.nb):
            ids=plan.block_cw[b]; g=gain[ids]; top=np.argsort(-g)[:bud]; top=top[g[top]>0]; flip_cw[ids[top]]=True
        sel=flip_cw[np.arange(R)//8]&mism; final[sel]=tgt[sel]
    cap_total=t_per_block*plan.nb
    mat=L.with_format(ECC_INFO[plan.ecl][1],mask); mat[ys,xs]=final; mat[L.ys[R:],L.xs[R:]]=target[L.ys[R:],L.xs[R:]]
    match=float((final==tgt).mean())
    return dict(matrix=mat,mask=mask,match=match,free_bits=nv,pivots=int(is_piv.sum()),version=plan.ver,cap_cw=cap_total,flipped_cw=0)

def prepare_target(gray, size, scale, ox, oy, method="Local", bias=0, edge_focus=0.6, clahe=True):
    S=6; big=size*S; s=scale*S
    img=gray
    if s < 1.0:
        img=cv2.GaussianBlur(img,(0,0),0.45/s)
    Mx=np.float32([[s,0,ox*S],[0,s,oy*S]])
    canvas=cv2.warpAffine(img,Mx,(big,big),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=255)
    inside_big=cv2.warpAffine(np.full(gray.shape,255,np.uint8),Mx,(big,big),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)>127
    if clahe:
        canvas=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(canvas)
        canvas[~inside_big]=255
    canvas=cv2.GaussianBlur(canvas,(0,0),S*0.3)
    inside=cv2.resize(inside_big.astype(np.float32),(size,size),interpolation=cv2.INTER_AREA)
    vals=canvas[inside_big]
    otsu=128.0
    if vals.size>100:
        otsu,_=cv2.threshold(vals.reshape(-1,1),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if method=="Halftone":
        g=cv2.resize(canvas,(size,size),interpolation=cv2.INTER_AREA).astype(np.float32)/255.0
        g=np.clip((g-otsu/255.0)*1.6+0.5-bias/255.0*1.5,0,1)
        out=g.copy(); tgt=np.zeros((size,size),np.uint8)
        for y in range(size):
            for x in range(size):
                old=out[y,x]; new=1.0 if old>0.5 else 0.0; tgt[y,x]=1-int(new); err=old-new
                if x+1<size: out[y,x+1]+=err*7/16
                if y+1<size:
                    if x>0: out[y+1,x-1]+=err*3/16
                    out[y+1,x]+=err*5/16
                    if x+1<size: out[y+1,x+1]+=err*1/16
        conf=np.full((size,size),0.5,np.float32); cov=1.0-g
    else:
        if method=="Local":
            fcanvas=canvas.astype(np.float32); wmask=inside_big.astype(np.float32)
            num=cv2.GaussianBlur(fcanvas*wmask+255*(1-wmask),(0,0),big/10.0)
            thr=0.5*otsu+0.5*num
        else:
            thr=otsu
        dark_big=(canvas.astype(np.float32) < thr + bias).astype(np.float32)
        cov=cv2.resize(dark_big,(size,size),interpolation=cv2.INTER_AREA)
        tgt=(cov>0.5).astype(np.uint8)
        conf=np.abs(cov-0.5)*2
    gx=cv2.Sobel(cov,cv2.CV_32F,1,0,ksize=3); gy=cv2.Sobel(cov,cv2.CV_32F,0,1,ksize=3)
    edge=np.sqrt(gx*gx+gy*gy); edge=edge/(edge.max()+1e-6)
    weight=0.15+0.5*conf+1.5*edge_focus*edge
    weight=weight*(0.25+0.75*inside)
    return tgt,weight.astype(np.float32),cov

def render_matrix(mat,scale=8,border=4):
    img=np.where(mat==1,0,255).astype(np.uint8); img=np.pad(img,border,constant_values=255)
    return cv2.resize(img,(img.shape[1]*scale,img.shape[0]*scale),interpolation=cv2.INTER_NEAREST)
def scan_check(mat,payload_text):
    img=render_matrix(mat,8); ok=[]
    try:
        d,_,_=cv2.QRCodeDetector().detectAndDecode(img)
        if d==payload_text: ok.append("OpenCV")
    except: pass
    if hasattr(cv2,"QRCodeDetectorAruco"):
        try:
            d,_,_=cv2.QRCodeDetectorAruco().detectAndDecode(img)
            if d==payload_text: ok.append("OpenCV-Aruco")
        except: pass
    if zxingcpp is not None:
        try:
            r=zxingcpp.read_barcodes(img)
            if r and r[0].text==payload_text: ok.append("ZXing")
        except: pass
    return ok
def make_square_lesser_side(gray):
    h,w=gray.shape[:2]; side=min(h,w); y0=(h-side)//2; x0=(w-side)//2
    return gray[y0:y0+side, x0:x0+side].copy()

# Page config + tight spacing CSS
st.set_page_config(page_title="QArt — QR Photo Art ST", layout="wide")
st.markdown("""
<style>
/* Reduce vertical gaps */
div[data-testid="stVerticalBlock"] { gap: 0.4rem; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 0.35rem; }
div[data-testid="stFileUploader"] { padding-top: 0.2rem; padding-bottom: 0.2rem; }
h3 { margin-top: 0.2rem; margin-bottom: 0.4rem; }
/* Make sidebar more compact */
.stSlider { margin-top: -0.4rem; margin-bottom: -0.4rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("## QArt — QR Photo Art ST")

# Init session
if "last_file_id" not in st.session_state: st.session_state.last_file_id=None
if "gray_square" not in st.session_state: st.session_state.gray_square=None
if "uploader_counter" not in st.session_state: st.session_state.uploader_counter=0
if "cropper_counter" not in st.session_state: st.session_state.cropper_counter=0

with st.sidebar:
    # 1. URL right at top
    st.markdown("**1. URL / text**")
    data_text = st.text_input("URL", "https://example.com/", label_visibility="collapsed", key="url_input")
    
    # 2. Load photo right below URL - compact
    st.markdown("**2. Load photo**")
    uploaded = st.file_uploader("Drag image or click Browse", type=["jpg","jpeg","png","bmp","webp"], key=f"uploader_{st.session_state.uploader_counter}", label_visibility="collapsed")
    
    # RESET / Reload buttons right nearby
    c_reset1, c_reset2 = st.columns(2)
    with c_reset1:
        if st.button("🔄 RESET view", use_container_width=True, help="Reset green box to full image"):
            st.session_state.cropper_counter += 1
            st.rerun()
    with c_reset2:
        if st.button("♻️ Reload image", use_container_width=True, help="Clear and reload a new image"):
            st.session_state.uploader_counter += 1
            st.session_state.last_file_id = None
            st.session_state.gray_square = None
            st.session_state.cropper_counter += 1
            st.rerun()

    st.divider()

    # Other controls - more compact now below
    st.markdown("**QR Settings**")
    ver_min = st.slider("Min QR version", 5, 20, 9)
    ecc = st.selectbox("ECC (L = most picture)", ["L","M","Q","H"], 0)
    method = st.selectbox("Photo mapping", ["Local","Otsu","Halftone"], 0)
    bias = st.slider("Black-white cutoff", -50, 50, 0)
    edge_focus = st.slider("Edge focus", 0.0, 1.0, 0.6)
    budget = st.slider("Spare ECC % for detail", 0, 100, 40)
    clahe = st.checkbox("Boost contrast (CLAHE)", True)
    ghost = st.checkbox("Show target overlay", False)
    live = st.checkbox("Live update as you drag", value=True)
    border = st.slider("PNG border", 2, 10, 4)
    scale_save = st.slider("PNG scale", 10, 60, 30)

if uploaded is not None:
    file_id = f"{uploaded.name}_{uploaded.size}_{st.session_state.cropper_counter}"
    file_bytes = np.asarray(bytearray(uploaded.getvalue()), dtype=np.uint8)
    gray_raw = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
    if max(gray_raw.shape) > 1200:
        f = 1200.0 / max(gray_raw.shape)
        gray_raw = cv2.resize(gray_raw, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    if file_id != st.session_state.last_file_id or st.session_state.gray_square is None:
        # Only update gray_square when file actually changes, keep cropper_counter for reset view
        if st.session_state.last_file_id is None or uploaded.name not in st.session_state.last_file_id:
            st.session_state.gray_square = make_square_lesser_side(gray_raw)
        st.session_state.last_file_id = file_id
    gray_square = st.session_state.gray_square

    col_left, col_right = st.columns([1.1, 0.9])

    with col_left:
        if HAS_CROPPER:
            st.caption(f"Green box = mapped area | {gray_square.shape[0]}x{gray_square.shape[0]} from {gray_raw.shape[1]}x{gray_raw.shape[0]}")
            pil_img = Image.fromarray(gray_square)
            cropped = st_cropper(pil_img, realtime_update=True, box_color='#00FF00', aspect_ratio=(1,1), return_type='image', key=file_id)
            cropped_np = np.array(cropped.convert('L'))
        else:
            st.warning("pip install streamlit-cropper")
            cropped_np = gray_square

    @st.cache_data(show_spinner=False)
    def solve_qr(cropped_bytes, data_text, ver_min, ecc, method, bias, edge_focus, budget, clahe):
        arr = np.frombuffer(cropped_bytes, dtype=np.uint8)
        cropped_np_inner = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        payload = data_text.encode()
        v = min_version_for(payload, ecc, ver_min)
        plan = get_plan(v, ecc)
        n = plan.layout.size
        h_c = cropped_np_inner.shape[0]
        scale_fix = n / h_c
        tgt, weight, cov = prepare_target(cropped_np_inner, n, scale_fix, 0.0, 0.0, method, bias, edge_focus, clahe)
        res = qart_solve(plan, payload, tgt, weight, budget/100.0)
        ok = scan_check(res["matrix"], data_text)
        return res, ok, tgt, cov

    with col_right:
        _, buf = cv2.imencode(".png", cropped_np)
        should_solve = live
        if not live:
            should_solve = st.button("Update QR window", type="primary", use_container_width=True)

        if should_solve:
            with st.spinner("Solving..."):
                res, ok, tgt, cov = solve_qr(buf.tobytes(), data_text, ver_min, ecc, method, bias, edge_focus, budget, clahe)
            if ok:
                st.success(f"Scans: {', '.join(ok)} | v{res['version']} mask {res['mask']} {res['match']*100:.0f}%")
            else:
                st.error("Not decodable - lower detail or raise version")
            preview = render_matrix(res["matrix"], 8, 4).astype(np.float32)
            if ghost:
                g = np.pad((1-cov)*255, 4, constant_values=255).astype(np.float32)
                import cv2 as cv2b
                g = cv2b.resize(g, (preview.shape[1], preview.shape[0]), interpolation=cv2.INTER_NEAREST)
                preview = preview*0.6 + g*0.4
            st.image(preview.clip(0,255).astype(np.uint8), width=420, caption="QR Preview")

            st.markdown("#### 💾 Save to PNG")
            hi = render_matrix(res["matrix"], scale_save, border)
            _, png = cv2.imencode(".png", hi)
            st.download_button(f"Download PNG {hi.shape[1]}x{hi.shape[0]} px", png.tobytes(), "portrait_qr.png", "image/png", type="primary", use_container_width=True)
            st.caption(f"free bits {res['free_bits']} pivots {res['pivots']} | {method} bias {bias:+d}")
        else:
            if not live:
                st.info("Press Update QR window")
else:
    st.info("Upload headshot in sidebar (right below URL). Use RESET view to recenter green box, Reload to clear image. Green box now maps fully (not just corner).")
    if not HAS_CROPPER:
        st.code("pip install streamlit-cropper", language="bash")

# For GitHub deploy note
st.sidebar.divider()
st.sidebar.caption("Deploy: If you rename this file to app.py, Streamlit Cloud will find it automatically. Or keep name and set Main file path to this file in deploy settings.")
