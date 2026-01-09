import json
import csv
import chardet
from collections import Counter
# Your data

t_decks = 'Top8SorceryCONdecklist.json'
cards_type = 'card_list_alpha.json'


# Open the JSON file
with open(t_decks, 'r', encoding='utf-8') as json_file:
    # Load the JSON data
    league_champ_deck_json  = json.load(json_file)
# Open the JSON file
with open(cards_type, 'r', encoding='utf-8') as json_file:
    # Load the JSON data
    cards_type_json  = json.load(json_file)
    



def find_card_percentage(card_name, decks, card_threshold):
    total_decks = len(decks)
    decks_with_card = 0
    type_counts = {'Air': 0, 'Water': 0, 'Fire': 0, 'Earth': 0}
    #print(card_name, card_threshold)
    all_sites = []
    for card in cards_type_json:
        if card['Element'] == 'Site':
            all_sites.append(card['Name'])
        
    #print(total_decks)

    for deck in decks:
        types = ['avatar', 'spellbook', 'atlas', 'sideboard']
        
        for type in types:
            for group in deck[type]:
                if card_name == group["name"]:
                    decks_with_card += 1
                    
            
        

                            
        #print(types_in_deck)

        #print(type_counts)
    
    percentage = (decks_with_card / total_decks) * 100

    return percentage



def find_total_card_count(card_name, decks, card_threshold):
    total_decks = len(decks)
    decks_with_card = 0
    count_of_card = 0 
    type_counts = {'Air': 0, 'Water': 0, 'Fire': 0, 'Earth': 0}
    #print(card_name, card_threshold)
    all_sites = []
    for card in cards_type_json:
        if card['Element'] == 'Site':
            all_sites.append(card['Name'])

    countofdecks = 0
    for deck in decks:
        sites_of_deck = []
        types_in_deck = []

        types = ['avatar', 'spellbook', 'atlas', 'sideboard']
        
        

        #print(deck_name)
        #print(first_key)
        #print(deck[first_key].keys())
        for type in types:
            for group in deck[type]:
                if card_name == group["name"]:
                    count_of_card += group['quantity']
                    
            
        

                            
        #print(types_in_deck)

        #print(type_counts)
        total_card_count = count_of_card
    return total_card_count

def find_decks_with_card_count(card_name, decks, card_threshold):
    total_decks = len(decks)
    decks_with_card = 0
    count_of_card = 0 
    type_counts = {'Air': 0, 'Water': 0, 'Fire': 0, 'Earth': 0}
    #print(card_name, card_threshold)
    all_sites = []
    for card in cards_type_json:
        if card['Element'] == 'Site':
            all_sites.append(card['Name'])

    countofdecks = 0
    for deck in decks:
        sites_of_deck = []
        types_in_deck = []

        types = ['avatar', 'spellbook', 'atlas', 'sideboard']
        
        for type in types:
            for group in deck[type]:
                if card_name == group["name"]:
                    countofdecks += 1
                    
            
        

                            
        #print(types_in_deck)

        #print(type_counts)
        total_card_count = countofdecks
    return total_card_count



def meta_threshold(decks, card_list):

    type_counts = {'Air': 0, 'Water': 0, 'Fire': 0, 'Earth': 0}

    #for card in cards_type_json:
    #    if card_threshold == 'Air':
    #        print(f"The total card count {card_name}: {card['Element']}")
    #        type_counts['Air'] +=1
    #    if card_threshold == 'Earth':
    #        print(f"The total card count {card_name}: {card['Element']}")
    #        type_counts['Earth'] +=1
    #    if card_threshold == 'Water':
    #        print(f"The total card count {card_name}: {card['Element']}")   
    #        type_counts['Water'] +=1
    #    if card_threshold == 'Fire':
    #        print(f"The total card count {card_name}: {card['Element']}")
    #        type_counts['Fire'] +=1

    #print(type_counts)
    elements_of_decks_counts = []
    elements_of_decks = []
    for deck in decks:
        elements_of_deck = []
        print(deck['name'])
        types = ['avatar', 'spellbook', 'atlas', 'sideboard']
        type_not_to_add = ['Avatar','AirFire', 'EarthFire', 'WaterFire', 'AirWaterFireEarth','None','AirEarth','WaterAir']
        for type in types:
            #print(type)
            for group in deck[type]:
                #print(group)
                for card in card_list:
                    if group['name'] == card['Name']:
                        card_info = card
                        #print(card_info)
                        if card['Threshold'] not in elements_of_deck and card['Threshold'] not in type_not_to_add:
                            elements_of_deck.append(card['Threshold'])
        print(elements_of_deck)
        elements_of_decks.append(elements_of_deck)
                            
        #print(types_in_deck)

        #print(type_counts)
    flattened_data = [tuple(sorted(sublist)) for sublist in elements_of_decks]
    counted_data = Counter(flattened_data)
    sorted_counts = sorted(counted_data.items(), key=lambda x: x[1], reverse=True)
    for sublist, count in sorted_counts:
        #print(f"{sublist}: {count}")
        elements_of_decks_counts.append((sublist, count))
    
    return elements_of_decks_counts



# Example usage
decks_data = league_champ_deck_json # Replace with your actual deck data
file_name = 'SorceryCon deck counts and Percentage top 8.csv'
file_name_Threshold = 'SorceryCon deck counts and Threshold top 8.csv'
card_percent = []
card_percent.append(['Name','Type','Total_count_of_card','Decks_with_card','Percentage of decks with at least one copy'])
for card in cards_type_json:
        percentage = find_card_percentage(card['Name'], decks_data, card['Threshold'])
        decks_with_card = find_decks_with_card_count(card['Name'], decks_data, card['Threshold'])
        total_count_of_card = find_total_card_count(card['Name'], decks_data, card['Threshold'])
        card_name_to_find = card['Name']
        #print(f"The percentage of decks to have {card_name_to_find}: {percentage}%")
        #print(f"The total decks to have one of the card {card_name_to_find}: {percentage}%")
        #print(f"The total decks with card{card_name_to_find}: {decks_with_card}")
        #print(f"The total card count {card_name_to_find}: {total_count_of_card}")
        card_percent.append([card['Name'],card['Type'],card['Rarity'],total_count_of_card,decks_with_card,round(percentage)])
#card_name_to_find = 'Apprentice Wizard'
#percentage = find_card_percentage(card_name_to_find, decks_data, 'Air')
print(meta_threshold(decks_data, cards_type_json))
#print(f"The percentage of decks that are eligible to have {card_name_to_find}: {percentage}%")

# Writing to CSV file
with open(file_name, 'w', newline='') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerows(card_percent)

with open(file_name_Threshold, 'w', newline='') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerows(meta_threshold(decks_data, cards_type_json))

print(f'Data has been saved to {file_name}') 
