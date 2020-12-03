#!/usr/bin/python
import sys
import json
from datetime import datetime, timedelta
import shutil
import requests
import numpy as np
import pandas as pd
import fcntl
import os



#Defining printout colors
class color:
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'
    GREEN = '\033[92m'
    UNDERLINE = '\033[4m'
    DARKCYAN = '\033[36m'
    YELLOW = '\033[93m'

def handleTime():
    '''
    Trigger: handleTime()
    Purpose: Gets time for printout and handles data maturity.
    '''
    #Get last update time.
    with open('config.json', 'r') as f:
        config = json.load(f)
    lastUpd = config['last_updated'].split(" ")
    currentTime = datetime.now()
    timeElapsed = currentTime - datetime.fromisoformat(config['last_updated'])

    #Get how much more time until 24 hours have elapsed since last "macven -u".
    timeToGo = (datetime.fromisoformat(config['last_updated']) + timedelta(1)) - currentTime
    times = [timeElapsed,timeToGo]

    #Create pretty time for printout.
    for i, t in enumerate(times):
        splTime = str(t).split(":")
        if splTime[0] == "0":
            times[i] = splTime[1] + "." +\
                str((int(splTime[2].split(".")[0])/60)*10)[:1] + " mins"
            if times[i][0] == "0": times[i] = times[i][1:]
        else:
            times[i] = splTime[0] + "." + str((int(splTime[1])/60)*10)[:1] + " hours"
    return (timeElapsed, times)

def getCSV():
    '''
    Trigger: macven -u
    Purpose: getCSV downloads the out.txt file at "http://standards-oui.ieee.org/oui.txt"
             and formats it's contents for efficient querying. Upon completion, the reformatted
             data is saved as a csv at /neteng/db/oui.csv.
    '''
    with open('config.json', 'r') as f:
        config = json.load(f)
    timeOb = handleTime()
    if timeOb[0] < timedelta(0):
        print('\n' + color.YELLOW + color.BOLD + "DATA NOT MATURE - " +color.END + color.YELLOW + "/" + config['csv_path'] + " was updated " +  timeOb[1][0] + " ago. Wait until " + str(timeOb[1][1]) + " have elapsed before attempting again." + color.END +'\n')
        return

    print("Retriving data...")

    #Resets the previous line in the terminal to keep the printout clean.
    sys.stdout.write("\033[F"); sys.stdout.write("\033[K")
    
    #Download txt file.
    try: 
        response = requests.get("http://standards-oui.ieee.org/oui.txt", stream=True)
    except: 
        print(
            '\n' + color.RED + color.BOLD + 'NETWORK ERROR  -' + color.END + color.RED + ' bad response from standards-oui.ieee.org/oui.txt' + color.END + '\n\
            > Check network connection.\n'
        )
        return
    if response.status_code == 200:
        with open("oui.txt", "wb") as f:
            print('Good response from standards-oui.ieee.org/oui.txt. Downloading...')
            sys.stdout.write("\033[F"); sys.stdout.write("\033[K")
            response.raw.decode_content = True
            shutil.copyfileobj(response.raw, f)
    else:
        print(
            '\n' + color.RED + color.BOLD + 'NETWORK ERROR  -' + color.END + color.RED + ' bad response from standards-oui.ieee.org/oui.txt' + color.END + '\n\
            > Check network connection.\n'
        )
        return

    #Formatting data and saving to csv.
    df = pd.read_csv("oui.txt", sep="\t\t", skiprows=1,
                     index_col=False, engine='python')
    df.reset_index(inplace=True)
    df.columns = ['MAC', 'Company']
    address = ""
    length = len(df)
    macIndexes = []
    isMac = False
    print("Formatting data...")
    sys.stdout.write("\033[F"); sys.stdout.write("\033[K")
    for index, row in df.iterrows():
        if row['Company'] == None:
            address = address + " " + row['MAC']
            isMac = True
            if index == length-1:
                for macIndex in macIndexes:
                    df.at[macIndex, 'Address'] = address
        else:
            if isMac:
                for macIndex in macIndexes:
                    df.at[macIndex, 'Address'] = address
                address = ""
                macIndexes = []
                isMac = False
            macIndexes.append(index)
            mac = row['MAC'].split(' (')
            df.at[index, 'Type'] = mac[1][:-1]
            df.at[index, 'MAC'] = mac[0]
    df = df.dropna().reset_index(drop=True)
    

    #Update config file. Note, writing in config file is locked to prevent concurrent writing. 
    #writing concurrently will cause failure and will prompt the user to try again.
    oConfig = {'last_updated': str(datetime.now()),
              'csv_path': config['csv_path']}
    try: 
        with open('config.json', 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(oConfig, f)
            fcntl.flock(f, fcntl.LOCK_UN)
    except:
        print(
            color.RED + color.BOLD + 'CONCURRENT WRITE ATTEMPT -' + color.END + color.RED + ' config.json was written to at the exact same time.' + color.END + '\n\
            > Try again in a bit. \n\
            > Check existing chron jobs.\n'
        )
    
    #Export to csv.
    df.to_csv(config['csv_path'])

    #Remove downloaded txt to keep low storage.
    os.remove("oui.txt")
    print(
            '\n' + color.GREEN + color.BOLD + 'RETRIVAL COMPLETE -' + color.END + color.GREEN + ' data saved to ' + config['csv_path'] + "." + color.END + '\n'
        )



def findMac(macArg):
    '''
    Trigger: macven <MAC address>
    Purpose: findMac searches for the inputted MAC address at /neteng/db/oui.csv and returns it's 
             permutations and vendor information. 
    '''
    
    if len(macArg) < 6:
        print(
            '\n' + color.RED + color.BOLD + 'TOO SHORT - ' + color.END + color.RED + 'Inputted MAC address ' + color.UNDERLINE + macArg + color.END + color.RED + ' produced an error.' + color.END + '\n\
            > Macven accepts all common formats (eg. MM:MM:MM:SS:SS:SS, MM-MM-MM-SS-SS-SS, MMM.MMM.SSS.SSS, MMMMMMSSSSSS) \n\
            > Macven accepts both full MAC addresses and the first six chars.\n'
        )
        return
    variations = [":", "-", "."]
    timeOb = handleTime()
    inputMac = macArg
    with open('config.json', 'r') as f:
        config = json.load(f)
    #Normalizing input for querying
    if len(macArg) != 6:
        c = True
        for v in variations:
            if v in macArg:
                splMac = macArg.split(v)
                c = False
                if v == ".":
                    inputMac = splMac[0] + splMac[1]
                    break
                inputMac = splMac[0] + splMac[1] + splMac[2]
                break
        if c:
            inputMac = macArg[:6]
    #create variations
    outMac = inputMac
    outMacs = []
    for variation in variations:
        try:
            outMac = outMac.split(variation)[0] + outMac.split(variation)[1] + outMac.split(variation)[2]
        except:
            pass

    #import csv as dataframe
    df = pd.read_csv(config['csv_path'], index_col=False, engine='python')

    #Query csv.
    try:
        vendor = df.loc[df['MAC'].str.match(outMac)].iloc[0, 2]
        outMacs.append(outMac + "  ")
        for v in variations:
            if v == ".":
                outMacs.append(outMac[0:3] + variation + outMac[3:6] + " ")
            else:
                outMacs.append(outMac[0:2] + v + outMac[2:4] + v + outMac[4:6])
        print(
            '\n' + color.GREEN + color.BOLD + 'SUCCESS - ' + color.END + color.GREEN + 'MAC address ' + color.UNDERLINE + macArg + color.END + color.GREEN + ' found.' + color.END + '\n')
        print("Variation ┃ Vendor")
        print("━━━━━━━━━━╋━━━━━━━━━━━━━━━━")
        for macForm in outMacs:
            print(macForm + "  ┃ " + vendor)
        print(color.DARKCYAN + '/' + config['csv_path'] + ' last updated ' +
              timeOb[1][0] + ' ago.' + color.END + '\n')
    except:
        print(
            '\n' + color.RED + color.BOLD + 'NOT FOUND - ' + color.END + color.RED + 'Inputted MAC address ' + color.UNDERLINE + macArg + color.END + color.RED + ' produced an error.' + color.END + '\n\
            > out.csv may be stale. /' + config['csv_path'] + ' was updated ' + timeOb[1][0] + ' ago.\n\
            > Check input, you inputted ' + color.UNDERLINE + macArg + color.END + '.\n'
        )


def getInfo():
    print('\n' + color.RED + '███╗   ███╗ █████╗  ██████╗██╗   ██╗███████╗███╗   ██╗\n████╗ ████║██╔══██╗██╔════╝██║   ██║██╔════╝████╗  ██║\n██╔████╔██║███████║██║     ██║   ██║█████╗  ██╔██╗ ██║\n██║╚██╔╝██║██╔══██║██║     ╚██╗ ██╔╝██╔══╝  ██║╚██╗██║\n██║ ╚═╝ ██║██║  ██║╚██████╗ ╚████╔╝ ███████╗██║ ╚████║\n╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═══╝  ╚══════╝╚═╝  ╚═══╝' + color.END)
    print('\n' + color.BOLD + 'macven -u ' + color.END + ':\n\
        > Retrives and saves all records at http://standards-oui.ieee.org/oui.txt as /neteng/db/out.csv. \n\
        > Will NOT update if file has been updated within 24 hours.\n \n'
          + color.BOLD + 'macven <MAC address> ' + color.END + ':\n\
        > Returns information for the given MAC address (from http://standards-oui.ieee.org/oui.txt). \n\
        > Accepts all common formats (eg. MM:MM:MM:SS:SS:SS, MM-MM-MM-SS-SS-SS, MMM.MMM.SSS.SSS, MMMMMMSSSSSS) \n\
        > Accepts both full MAC addresses and the first six chars.\n'
          )


if len(sys.argv) == 1:
    getInfo()
elif sys.argv[1] == "-u":
    getCSV()
else:
    findMac(sys.argv[1])
if len(sys.argv) > 2:
    print('\n' +color.YELLOW + color.BOLD + "EXTRANEOUS ARGUMENT(S) -" +color.END + color.YELLOW + ' Enter "macven" to see list of commands.\n')


