import re
import datetime

def commandCharsToSerial(command):
  command = command.replace(" ", "")
  originalCmd = command
  command = re.findall('.{1,2}', command)
  length = len(command)
  
  chkSum = 0
  if (length > 2):
    for i in command:
      chValue = int("0x"+i, 16);
      chkSum += chValue

    chValue = chkSum % 256
    hexChValue = format(chValue, 'x')
    hexChValue = "0"+hexChValue if len(hexChValue) < 2 else hexChValue
    originalCmd += hexChValue;
  return originalCmd

def getTimeToSetMCU():
  """
  Command: Set date and time
	                       ?? YY MM DD HH MM SS Weekday
	DEC:                   01 19 02 15 16 04 18 05
	HEX: 55 AA 00 1C 00 08 01 13 02 0F 10 04 12 05
	DEC:                   01 19 02 20 17 51 44 03
	HEX: 55 AA 00 1C 00 08 01 13 02 14 11 33 2C 03
  """
  date = datetime.datetime.now()
  year = date.year - 2000
  month = date.month
  dayOfMonth = date.day
  hours = date.hour
  minutes = date.minute
  seconds = date.second
  dayOfWeek = date.isoweekday()
  
  baseString = "55 AA 00 1C 00 08 01"
  command = baseString
  command += stringToHex(year)  
  command += stringToHex(month)  
  command += stringToHex(dayOfMonth)  
  command += stringToHex(hours)
  command += stringToHex(minutes) 
  command += stringToHex(seconds) 
  command += stringToHex(dayOfWeek)
  
  return commandCharsToSerial(command)


def stringToHex(num):
    num = format(num, 'x')
    num = "0"+num if len(num) < 2 else num
    return num