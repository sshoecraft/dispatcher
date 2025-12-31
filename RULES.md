**MANDATORY SERVER COMMANDS (NEVER DEVIATE):**
- To start the Frontend: `cd <cwd> && ./start_frontend.sh > ~/dispatcher/logs/frontend.log 2>&1 &`
- To stop the Frontend: `cd <cwd> && ./stop_frontend.sh` then MAKE SURE all processes have exited (including workers)
- To start the Backend: `cd <cwd> && ./start_backend.sh > ~/dispatcher/logs/backend.log 2>&1 &`
- To stop the Backend: `cd <cwd> && ./stop_backend.sh`
- After starting either frontend or backend, check to see if they are running: `lsof -Pi | grep LISTEN`
- **POLL FOR SERVER READINESS**: Use `tail -n 10 <logfile>` repeatedly with `sleep 5` between checks until log shows startup completion message
- **ONLY AFTER** log confirms server is ready, verify port is listening: `lsof -Pi | grep LISTEN`
- **Final verification**: `curl -I http://<network ip>:<port number>` returns HTTP 200
- **CRITICAL**: To rebuild frontend, use the proecess to start the frontend, it automatically rebuilds and starts the frontend (NEVER use npm run build directly)
- **IMPORTANT**: Do NOT change ngnix config or config.json or config.local.json - they are changed by start_frontend.sh! if you need to make config changes, change start_frontend.sh!
- **MANDATORY**: Anytime you change ANY frontend files (.tsx, .ts, .css, etc.), you MUST restart the frontend using the proper process
- **CRITICAL**: DO NOT EVER CALL /api/database/initialize!!!
- ANY TIME you update the functionality of any component of the system you need to incremenet the version of that component

**RESTART WORKFLOW - YOU MUST FOLLOW THIS EXACTLY:**
After ANY code change:
1. BACKEND CHANGES (*.py files in backend/): 
   - STOP: `./stop_backend.sh`
   - START: `./start_backend.sh > ~/dispatcher/logs/backend.log 2>&1 &`
   - WAIT: Check logs with `tail -n 10 ~/dispatcher/logs/backend.log` until "Application startup complete"
   
2. FRONTEND CHANGES (*.tsx, *.ts, *.css in frontend/):
   - STOP: `./stop_frontend.sh`  
   - START: `./start_frontend.sh > ~/dispatcher/logs/frontend.log 2>&1 &`
   - WAIT: Check logs until "Nginx server is ready and running!"

**WHEN TO RESTART:**
- Complete ALL related changes first (batch your work)
- THEN restart once when all changes are done
- Only restart immediately if you need to test that specific change
**IF USER REPORTS AN ERROR, FIRST CHECK IF YOU FORGOT TO RESTART**
**REMEMBER: Changes don't take effect until you restart the affected service**

**WORKER INSTRUCTIONS:**
- After any changes to worker/ (dispatcher_worker), you need to rebuild the wheel file and install it in $PREFIX/lib
- DO NOT make any changes to the deployed dispatcher_worker!!! always make changes to the worker in the source tree then build, deploy, install
- YOU MUST use the $PREFIX/venv when installing the package via pip3!!!  (source $PREFIX/venv/bin/activate && pip3 install -e worker/)
- DO NOT start any worker manually!  Always use the backend api unless expressely told to do so!
