

from volontaire.utils import get_info
from volontaire.models  import MachineInfo

def register_in_bd():
    info = get_info()
    machine = MachineInfo(
        
    ).save()

    # enregister au niveau de .volunteer_app/volunteer_info.json
    return