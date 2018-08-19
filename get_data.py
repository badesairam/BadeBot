import sys
import re
import json
import numpy
#iconv -c -f utf-8 -t ascii text_tmp
#remove <Media omitted> and the lines corresponding to it
#remove hperlinks sed -n '/http\?s/p'
#sed ':a;$!N;s/\n/###/g;ta' f1.txt | sed 's/###\([0-9]\{1,2\}\/[0-9]\{1,2\}\/[0-9]\{2\}\)/##\1/g' | sed 's/###/ /g' | sed 's/##/\n/g'
def getWhatsApp(file):
	responseDictionary = dict()
	waFile = open(file, 'r') 
	allLines = waFile.readlines()
	myMessage, otherPersonsMessage, currentSpeaker = "","",""
	for index,lines in enumerate(allLines):
		colon = lines.find(':')
		justMessage = lines
		# Find messages that I sent
		if (justMessage[1:colon] == "Sairam Bade" ):
			if not myMessage:
				# Want to find the first message that I send (if I send multiple in a row)
				startMessageIndex = index - 1
			myMessage += justMessage[colon+2:]
		elif myMessage:
			# Now go and see what message the other person sent by looking at previous messages
			for counter in range(startMessageIndex, -1, -1):
				justMessage = allLines[counter]
				colon = justMessage.find(':')
				if not currentSpeaker:
					# The first speaker not named me
					currentSpeaker = justMessage[1:colon]
				elif (currentSpeaker != justMessage[1:colon] and otherPersonsMessage):
					# A different person started speaking, so now I know that the first person's message is done
					otherPersonsMessage = cleanMessage(otherPersonsMessage)
					myMessage = cleanMessage(myMessage)
					responseDictionary[otherPersonsMessage] = myMessage
					break
				otherPersonsMessage = justMessage[colon+2:] + otherPersonsMessage
			myMessage, otherPersonsMessage, currentSpeaker = "","","" 
	return responseDictionary

def getFb(file):
	responseDictionary = dict()
	waFile = open(file, 'r') 
	allLines = waFile.readlines()
	myMessage, otherPersonsMessage, currentSpeaker = "","",""
	for index,lines in enumerate(allLines):
		colon = lines.find(':')
		justMessage = lines
		# Find messages that I sent
		if (justMessage[:colon-1] == "Sairam Bade" ):
			if not myMessage:
				# Want to find the first message that I send (if I send multiple in a row)
				startMessageIndex = index - 1
			myMessage += justMessage[colon+2:]
		elif myMessage:
			# Now go and see what message the other person sent by looking at previous messages
			for counter in range(startMessageIndex, -1, -1):
				justMessage = allLines[counter]
				colon = justMessage.find(':')
				# print(justMessage[:colon-1])
				# print(currentSpeaker)
				if not currentSpeaker:
					# The first speaker not named me
					currentSpeaker = justMessage[:colon-1]
				elif (currentSpeaker != justMessage[:colon-1] and otherPersonsMessage):
					# A different person started speaking, so now I know that the first person's message is done
					otherPersonsMessage = cleanMessage(otherPersonsMessage)
					myMessage = cleanMessage(myMessage)
					responseDictionary[otherPersonsMessage] = myMessage
					break
				otherPersonsMessage = justMessage[colon+2:] + otherPersonsMessage
			myMessage, otherPersonsMessage, currentSpeaker = "","","" 
	return responseDictionary

def cleanMessage(message):
	# Remove new lines within message
	cleanedMessage = message.replace('\n',' ').lower()
	# Deal with some weird tokens
	cleanedMessage = cleanedMessage.replace("\xc2\xa0", "")
	# Remove punctuation
	cleanedMessage = re.sub('([.,!?-_\'])','', cleanedMessage)
	# Remove multiple spaces in message
	cleanedMessage = re.sub(' +',' ', cleanedMessage)
	# Remove multiple letters 
	cleanedMessage = re.sub(r'([a-zA-Z])\1+', r'\1',cleanedMessage)
	#Remove numbers more than 3 digits
	cleanedMessage = re.sub('[0-9]{3,}','',cleanedMessage)
	return cleanedMessage

combinedDictionary = {}
wafiles = open('WhatsAppfileslist','r')
for wafile in wafiles:
	combinedDictionary.update(getWhatsApp(wafile.strip('\n')))
fbfiles = open('Facebookfileslist','r')
for fbfile in fbfiles:
	combinedDictionary.update(getFb(fbfile.strip('\n')))

print(len(combinedDictionary))

numpy.save("conversationData.npy",combinedDictionary)

conversationFile = open('conversationData.txt', 'w')
for key,value in combinedDictionary.items():
	# if (not key.strip() or not value.strip()):
	# 	# If there are empty strings
	# 	continue
	if(key == ""):
		del combinedDictionary[key]
	elif(value == " "):
		combinedDictionary[key] = "ok"

print(len(combinedDictionary))

for key,value in combinedDictionary.items():
	conversationFile.write(key.strip() +" \n" +value.strip() + "\n")

#grep -o -E '\w+' conversationData.txt | sort -u -f > wordList.txt