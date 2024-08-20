from __future__ import annotations
__all__ = ['ipm']
def ipm(cmd, *args):
    """
    
        Executes shell command with IPM:
        Parameters
        ----------
        cmd : str
            The command to execute
        Examples
        --------
        `ipm('help')`
        `ipm('load /home/irisowner/dev -v')`
        `ipm('install webterminal')`
        
    """
