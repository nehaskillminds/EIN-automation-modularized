from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from .models import CaseData
from .irs_ein import IRSEINAutomation
from .config import CONFIG
import logging

logger = logging.getLogger(__name__)

# FastAPI Application
app = FastAPI(title="IRS EIN API", description="Automated IRS EIN form processing with Azure AD auth", version="2.0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    try:
        # Verify database/azure connections if needed
        return {"status": "ok", "details": {"chromium": "available"}}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/run-irs-ein")
async def run_irs_ein_endpoint(
    request: Request,
    # user: dict = Depends(get_current_user)
):
    """Main endpoint for running IRS EIN automation with direct submission"""
    data = await request.json()
    json_data = data
    logger.info(f"Received request from: {request.client.host if request.client else 'Unknown'}")

    try:
        data = await request.json()
        logger.info(f"Received payload: {json.dumps(data, indent=2)}")
        
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Invalid payload format - expected JSON object")
        
        required_fields = ["entityProcessId", "formType"]
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            raise HTTPException(status_code=400, detail=f"Missing required fields: {missing_fields}")
        
        if data.get("formType") != "EIN":
            raise HTTPException(status_code=400, detail="Invalid formType, must be 'EIN'")
        
        case_data = DataProcessor.map_form_automation_data(data)
        logger.info(f"Mapped case data for record_id: {case_data.record_id}")
        
        automation = IRSEINAutomation()
        try:
            success, message, azure_blob_url = await automation.run_automation(case_data)
            if success:
                return {
                    "message": "Form submitted successfully",
                    "status": "Submitted",
                    "record_id": case_data.record_id,
                    "azure_blob_url": azure_blob_url
                }
            else:
                raise HTTPException(status_code=400, detail=message)

        except Exception as e:
            logger.error(f"Top-level endpoint error: {str(e)}")
            trace = traceback.format_exc()
            record_id = data.get("entityProcessId") or data.get("record_id", "unknown")
            json_data["record_id"] = record_id
            json_data["error_message"] = "automation failed"
            json_data["exception"] = str(e)
            json_data["traceback"] = traceback.format_exc()
            json_data["response_status"] = "fail"

            automation._save_json_data_sync(json_data, case_data, file_name="Failure_Data.json")



            raise HTTPException(status_code=500, detail="Automation failed at top level")

    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Endpoint error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")