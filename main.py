import os
import uuid
import datetime

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# -------------------------
# Basic setup
# -------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = "sqlite:///./protein.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)
app.mount(
    "/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads"
)


# -------------------------
# Models
# -------------------------

class Protein(Base):
    __tablename__ = "proteins"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True)  # used in URL
    filename = Column(String)
    sequence = Column(String)   # full sequence (1-letter)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    annotations = relationship("Annotation", back_populates="protein")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    protein_id = Column(Integer, ForeignKey("proteins.id"))
    start_index = Column(Integer)   # 0-based inclusive
    end_index = Column(Integer)     # 0-based inclusive
    label = Column(String)
    color = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    protein = relationship("Protein", back_populates="annotations")


Base.metadata.create_all(bind=engine)


# -------------------------
# Helper: parse sequence from PDB
# Very simple: collects residues in order, maps 3-letter -> 1-letter.
# -------------------------

RES3_TO_1 = {
    "ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E",
    "PHE": "F", "GLY": "G", "HIS": "H", "ILE": "I",
    "LYS": "K", "LEU": "L", "MET": "M", "ASN": "N",
    "PRO": "P", "GLN": "Q", "ARG": "R", "SER": "S",
    "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y",
}

def extract_sequence_from_pdb(pdb_path: str) -> str:
    residues_seen = set()
    sequence = []

    with open(pdb_path, "r") as f:
        for line in f:
            if not line.startswith("ATOM"):
                continue

            res_name = line[17:20].strip()
            chain_id = line[21].strip()
            res_seq = line[22:26].strip()

            key = (chain_id, res_seq)
            if key in residues_seen:
                continue
            residues_seen.add(key)

            aa = RES3_TO_1.get(res_name, "X")
            sequence.append(aa)

    return "".join(sequence)


# -------------------------
# Dependency
# -------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------
# Routes
# -------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload", response_class=HTMLResponse)
async def upload_pdb(request: Request, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdb"):
        raise HTTPException(status_code=400, detail="Please upload a .pdb file.")

    # Save file
    slug = uuid.uuid4().hex[:10]
    save_name = f"{slug}.pdb"
    save_path = os.path.join(UPLOAD_DIR, save_name)

    with open(save_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Parse sequence
    sequence = extract_sequence_from_pdb(save_path)

    # Store in DB
    from fastapi import Depends
    db = next(get_db())
    protein = Protein(
        slug=slug,
        filename=save_name,
        sequence=sequence,
    )
    db.add(protein)
    db.commit()
    db.refresh(protein)

    # Redirect to unique URL
    return RedirectResponse(url=f"/p/{protein.slug}", status_code=303)


@app.get("/p/{slug}", response_class=HTMLResponse)
def view_protein(slug: str, request: Request):
    db = next(get_db())
    protein = db.query(Protein).filter(Protein.slug == slug).first()
    if not protein:
        raise HTTPException(status_code=404, detail="Protein not found")

    annotations = (
        db.query(Annotation)
        .filter(Annotation.protein_id == protein.id)
        .order_by(Annotation.created_at.asc())
        .all()
    )

    # Provide annotations as a list of dicts to JS
    ann_data = [
        {
            "id": a.id,
            "start_index": a.start_index,
            "end_index": a.end_index,
            "label": a.label,
            "color": a.color,
        }
        for a in annotations
    ]

    return templates.TemplateResponse(
        "protein.html",
        {
            "request": request,
            "protein": protein,
            "annotations": ann_data,
            "pdb_url": f"/uploads/{protein.filename}",
            "share_url": f"{request.url.scheme}://{request.headers.get('host')}/p/{slug}",
        },
    )


@app.post("/p/{slug}/annotations")
async def add_annotation(
    slug: str,
    start_index: int = Form(...),
    end_index: int = Form(...),
    label: str = Form(...),
    color: str = Form(...),
):
    db = next(get_db())
    protein = db.query(Protein).filter(Protein.slug == slug).first()
    if not protein:
        raise HTTPException(status_code=404, detail="Protein not found")

    if start_index < 0 or end_index >= len(protein.sequence) or start_index > end_index:
        raise HTTPException(status_code=400, detail="Invalid index range")

    ann = Annotation(
        protein_id=protein.id,
        start_index=start_index,
        end_index=end_index,
        label=label,
        color=color,
    )
    db.add(ann)
    db.commit()

    return {"status": "ok"}
