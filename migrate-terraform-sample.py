import sys
import os
import keyboard
import time
import datetime
import re
import subprocess
import argparse
from colorama import Fore, Back, Style
import json
from enum import Enum
import shutil

import openai
from azure.identity import AzureCliCredential

# Azure OpenAI settings
OPENAI_API_BASE                 = 'https://openai-content-selfserv.openai.azure.com/'
OPENAI_VERSION                  = '2023-07-01-preview' # This may change in the future.
OPENAI_API_TYPE                 = 'azure_ad'
OPENAI_ENGINE                   = 'gpt-4-32k-moreExpensivePerToken'

openai.api_base     = OPENAI_API_BASE
openai.api_version  = OPENAI_VERSION

credential = AzureCliCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")

openai.api_type     = OPENAI_API_TYPE
openai.api_key      = token.token

# App constants
SETTINGS_FILE_NAME              = 'settings.json'
PROMPT_FILE_NAME                = 'prompt.json'
COMPLETION_FILE_NAME            = 'completion.txt'
MAX_SAMPLES_TO_PRINT            = 5
OUTPUT_DIRECTORY_NAME           = 'outputs'
TEMP_DIRECTORY_NAME             = 'temp'
TEST_RECORD_FILE_NAME           = 'TestRecord.md'

# App globals
sample_root_path                = ''
settings_before_and_after_dirs  = {}
directories_to_process          = []
sample_inputs_source            = []
sample_outputs_source           = []
debug_mode                      = False
output_path                     = ''
temp_path                       = ''

class AppMode(Enum):
    PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION    = 1
    CONFIRM_CONTINUE_AFTER_EACH_SAMPLE          = 2

app_mode = AppMode.CONFIRM_CONTINUE_AFTER_EACH_SAMPLE

class PrintDisposition(Enum):
    SUCCESS = 1
    WARNING = 2
    ERROR   = 3
    UI      = 4
    DEBUG   = 5
    STATUS  = 6

def print_message(text = '', disp = PrintDisposition.STATUS, override_indent = False):

    if disp == PrintDisposition.DEBUG and not debug_mode:
        return

    if not override_indent and debug_mode:
        text = "\t" + text

    if disp == PrintDisposition.SUCCESS:
        color = Fore.GREEN
    elif disp == PrintDisposition.WARNING:
        color = Fore.YELLOW
    elif disp == PrintDisposition.ERROR:
        color = Fore.RED
    elif disp == PrintDisposition.UI:
        color = Fore.LIGHTBLUE_EX
    elif disp == PrintDisposition.DEBUG:
        color = Fore.MAGENTA
    else: # disp == PrintDisposition.STATUS
        color = Fore.WHITE

    print(color + text + Style.RESET_ALL, flush=True)

def write_file(file_name, contents):
    try:
        with open(file_name, "w") as f:
            f.write(contents)
    except OSError as error:
        print_message(f"Failed to write file: {error}", PrintDisposition.ERROR)

def write_dictionary_to_file(file_name, dictionary):
    try:
        with open(file_name, "w") as f:
            f.write(json.dumps(dictionary, indent=4))
    except OSError as error:
        print_message(f"Failed to write file: {error}", PrintDisposition.ERROR)

def generate_new_sample(sample_dir):
    print_message(f"\nGenerating new sample...", PrintDisposition.DEBUG, override_indent=True)

    completion = ''

    try:
        messages = []

        # for every item in sample_inputs_source...
        for i in range(len(sample_inputs_source)):
            messages.append({"role": "user", "content": sample_inputs_source[i]})
            messages.append({"role": "assistant", "content": sample_outputs_source[i]})

        sample_source = get_terraform_source_code(sample_dir, include_file_names=False)
        messages.append({"role": "user", "content": sample_source})

        if debug_mode: # Write the prompt to a file.
            curr_sample_temp_path = get_normalized_path(sample_dir, temp_path)
            curr_sample_temp_path = os.path.join(curr_sample_temp_path, PROMPT_FILE_NAME)
            print_message(f"Prompt file path: {curr_sample_temp_path}", PrintDisposition.DEBUG)

            try:
                print_message(f"Creating directory path: {curr_sample_temp_path}", PrintDisposition.DEBUG)
                os.makedirs(os.path.dirname(curr_sample_temp_path),exist_ok=True)

                print_message(f"Writing Azure OpenAI prompt to: {curr_sample_temp_path}...", PrintDisposition.DEBUG)
                write_dictionary_to_file(curr_sample_temp_path, messages)
            except OSError as error:
                raise ValueError(f"Failed to create temp directory. {error}") from error

        special_chars = '\n'
        if debug_mode:
            special_chars = special_chars + '\t'
        print_message(f"{special_chars}Calling OpenAI for {sample_dir}...")
        time.sleep(1)

        response = openai.ChatCompletion.create(engine=OPENAI_ENGINE,
                                                messages=messages,
                                                temperature=0
                                                )
                                                
        if response:
            completion = response['choices'][0]['message']['content']
    except OSError as error:
        print_message(f"Failed to generate new sample. {error}", PrintDisposition.ERROR)

    time.sleep(1)

    if debug_mode: # Write the completion to a file.
        curr_sample_temp_path = get_normalized_path(sample_dir, temp_path)
        curr_sample_temp_path = os.path.join(curr_sample_temp_path, COMPLETION_FILE_NAME)
        print_message(f"Completion file path: {curr_sample_temp_path}", PrintDisposition.DEBUG)

        try:
            print_message(f"Creating directory path: {curr_sample_temp_path}", PrintDisposition.DEBUG)
            os.makedirs(os.path.dirname(curr_sample_temp_path),exist_ok=True)

            print_message(f"Writing Azure OpenAI completion to: {curr_sample_temp_path}...", PrintDisposition.DEBUG)
            write_file(curr_sample_temp_path, completion)
        except OSError as error:
            raise ValueError(f"Failed to create temp directory. {error}") from error
    
    return completion

def get_input_source(args):

    for i, (before, after) in enumerate(settings_before_and_after_dirs.items()):
        sample_inputs_source.append(get_terraform_source_code(before, include_file_names=False))
        sample_outputs_source.append(get_terraform_source_code(after, include_file_names=True))

def list_to_string(input_list):

    # Initialize an empty string.
    return_string = ""

    # Traverse elements of list...
    for list_element in input_list:

        # Add element to string.
        return_string += list_element

    # Return string.
    return return_string

def get_file_contents(file):
    file_contents = ""

    with open(file, encoding="utf-8") as f:
        file_contents = f.readlines()

    file_contents = list_to_string(file_contents)
    return file_contents

def get_terraform_source_code(dir, include_file_names):
    current_sample_source_code = ""

    # For every file in the source directory...
    for file_name in os.listdir(dir):

        if os.path.isfile(os.path.join(dir, file_name)):        

            # DO NOT process TestRecord.md file...
            if file_name != TEST_RECORD_FILE_NAME and file_name != '':
                
                # Append source code for the current directory/file
                if include_file_names:
                    current_file_source_code = ("###" 
                    + file_name 
                    + "###" 
                    + "\n" 
                    + get_file_contents(os.path.join(dir, file_name))
                    + "\n" 
                    + file_name 
                    + ":end\n")
                else:
                    current_file_source_code = ("\n" + get_file_contents(os.path.join(dir, file_name)))

                current_sample_source_code += current_file_source_code

    # Return the source code for the specified directory.
    return current_sample_source_code

def file_exists(path):
    return os.path.exists(path)

def parse_args():
    # Configure argParser for user-supplied arguments.

    argParser = argparse.ArgumentParser()
    argParser.add_argument("-s", 
                           "--sample_directory", 
                           help="Name of input sample directory.", 
                           required=True)

    argParser.add_argument("-r", 
                           "--recursive", 
                           action=argparse.BooleanOptionalAction,
                           help="Processes all subdirectories of specified SAMPLE_DIRECTORY'.", 
                           required=False)

    argParser.add_argument("-d", 
                           "--debug", 
                           action=argparse.BooleanOptionalAction,
                           help="Outputs verbose messaging and files to help with debugging.", 
                           required=False)

    return argParser.parse_args()

def create_new_sample(sample_dir):

    success = True

    # Generate the new sample and get the Azure OpenAI completion string.
    completion = generate_new_sample(sample_dir)

    # Write the sample file(s).
    write_new_sample(sample_dir, completion)

def get_normalized_path(sample_dir, output_path):

    # Get the last directory in the sample_root_path.
    # Example: C:\temp\migrate-terraform-sample\batch ==> batch
    relative_stub_root = os.path.basename(os.path.normpath(sample_root_path))

    # Remove sample_root_path from sample_dir to get the sample's relative path.
    # Example: C:\temp\migrate-terraform-sample\batch\basic\sample1\coolio ==> 
    # basic\sample1\coolio
    relative_sample_path = sample_dir.replace(sample_root_path, '')

    # Remove leading slash from relative_sample_path.
    relative_sample_path = relative_sample_path[1:]

    # Join output_path + relative_stub_root.
    # Example: C:\Users\tarcher\source\repos\migrate-terraform-sample\output
    #        + batch
    #        = C:\Users\tarcher\source\repos\migrate-terraform-sample\output\batch
    output_dir = os.path.join(output_path, relative_stub_root)

    # Join output_dir + relative_sample_path to get the final value to return.
    # Example: C:\Users\tarcher\source\repos\migrate-terraform-sample\output\batch
    #        + basic\sample1\coolio
    #        = C:\Users\tarcher\source\repos\migrate-terraform-sample\output\batch\basic\sample1\coolio
    output_dir = os.path.join(output_dir, relative_sample_path)

    return output_dir

def write_new_sample(sample_dir, file_contents):
    # Write the completion string to the appropriate files
    # based on the file markers within the completion.

    # Get the output path for the sample.
    sample_output_path = get_normalized_path(sample_dir, output_path)
    print_message(f"sample_output_path={sample_output_path}", PrintDisposition.DEBUG)

    # Create the directory for the sample.
    print_message(f"Creating directory for sample output: {sample_output_path}", PrintDisposition.DEBUG)
    os.makedirs(sample_output_path, exist_ok = True)

    if file_contents:
        file_names = re.findall(r'###(.*)###', file_contents)

        if file_names:
            for i in range(len(file_names)):
                current_file = file_names[i]

                beg_m = re.search('###'+ current_file + '###', file_contents)
                if beg_m:
                    end_m = re.search(current_file + ':end', file_contents)
                    if end_m:
                        sub = file_contents[(beg_m.span())[1]:(end_m.span())[0]]
                        sub = sub.strip()

                        curr_qfn = os.path.join(sample_output_path, current_file)
                        print_message("Writing file: " + curr_qfn, PrintDisposition.DEBUG)

                        try:
                            # Write the file.
                            with open(curr_qfn, "w") as f:
                                print_message("", PrintDisposition.DEBUG)
                                f.write(sub)
                        except OSError as error:
                            raise ValueError(f"Failed to write file. {error}") from error
                    else:
                        raise ValueError('Failed to find the end of the file name.')
                else:
                    raise ValueError('Failed to find the beginning of the file name.')
        else:
            raise ValueError('Failed to find any file names in the completion.')
    else:
        raise ValueError('Failed to get a valid completion from OpenAI.')

def init_app(args):

    # Set global debugging flag based on command-line arg.        
    if args.debug:
        global debug_mode
        debug_mode = True

    print_message("\nInitializing application...", PrintDisposition.DEBUG, override_indent=True)

    if debug_mode:
        print_message("Debugging enabled.", PrintDisposition.DEBUG)

    # Set the sample root path based on the command-line arg.
    global sample_root_path
    sample_root_path = os.path.abspath(args.sample_directory)
    print_message(f"Sample root path: {sample_root_path}", PrintDisposition.DEBUG)

    if not file_exists(sample_root_path):
        raise ValueError(f"Sample directory not found: {sample_root_path}")

    # Get the application path.
    application_path = ''
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)
    print_message(f"Application path: {application_path}", PrintDisposition.DEBUG)

    # Verify that the application path was found.
    if application_path == '':
        raise ValueError('Failed to get application path.')

    # Set the output path based on the application path.
    global output_path
    output_path = os.path.join(application_path, OUTPUT_DIRECTORY_NAME)
    print_message(f"Output path: {output_path}", PrintDisposition.DEBUG)

    # Set the temp path based on the application path.
    global temp_path
    temp_path = os.path.join(application_path, TEMP_DIRECTORY_NAME)
    print_message(f"Temp path: {temp_path}", PrintDisposition.DEBUG)

    # If output path doesn't exist, create it.
    if not os.path.exists(output_path):
        try:
            print_message("Creating output path...", PrintDisposition.DEBUG)
            os.mkdir(output_path)
        except OSError as error:
            raise ValueError(f"Failed to create output directory. {error}") from error
        
    # If temp path doesn't exist, create it.
    if not os.path.exists(temp_path):
        try:
            print_message("Creating temp path for sample...", PrintDisposition.DEBUG)
            os.mkdir(temp_path)
        except OSError as error:
            raise ValueError(f"Failed to create temp directory. {error}") from error

    # Get directory names for before and after samples.
    get_before_and_after_sample_dirs_from_settings_file()

    # Get the directories (samples) to process.
    get_directories_to_process(args)

    print_message("Application initialized.", PrintDisposition.DEBUG, override_indent=True)
    
def get_before_and_after_sample_dirs_from_settings_file():

    print_message("Getting before and after sample directories from settings file...", PrintDisposition.DEBUG)

    try:
        # Open the Inputs file.
        with open(SETTINGS_FILE_NAME) as inputs_file:
            # Load the JSON inputs file.
            inputs = json.load(inputs_file)
    except OSError as error:
        raise ValueError(f"Failed to open settings file ({SETTINGS_FILE_NAME}). {error}") from error

    # Each line is an input and there needs to be at least one line (input).
    if 1 > len(inputs):
        raise ValueError('At least one input/output pair must be specified in the inputs file.')

    # For each line in the file (representing a sample)...
    for i, (input, output) in enumerate(inputs.items()):
        if not file_exists(input):
            raise ValueError(f"[{SETTINGS_FILE_NAME}] Input file not found: {input}")
        if not file_exists(output):
            raise ValueError(f"[{SETTINGS_FILE_NAME}] Output file not found: {output}")
        settings_before_and_after_dirs[input] = output

def get_directories_to_process(args):

    print_message("Getting directories to process...", PrintDisposition.DEBUG)

    global directories_to_process

    # If the specified sample dir (root) exists...
    if file_exists(sample_root_path):

        # Add the root to the list.
        if len([1 for x in list(os.scandir(sample_root_path)) if x.is_file()]) > 0:
            directories_to_process.append(sample_root_path)

        # If recursive flag is set...
        if args.recursive:

            # For every directory in the sample dir...
            for root, dirs, files in os.walk(sample_root_path):

                # For every directory in the sample dir...
                for dir in dirs:

                    # Add the directory to the list.
                    if len([1 for x in list(os.scandir(os.path.join(root, dir))) if x.is_file()]) > 0:
                        directories_to_process.append(os.path.abspath(os.path.join(root, dir)))
    else:
        raise ValueError(f"Sample directory not found: {sample_root_path}")

def print_plan(args):
    print_message("\nPrinting the plan...", PrintDisposition.DEBUG, override_indent=True)

    if 0 == len(directories_to_process):
        print_message(f"There are no files to process in the specified directory: '{sample_root_path}'" + (" (including its subdirectories)" if args.recursive else "") + ".", PrintDisposition.UI)
    else:
        print_message()
        print_message("***IMPORTANT***: The Skilling org pays for the use of the Azure OpenAI service based on the number of tokens in the request & response for each generated sample.", PrintDisposition.WARNING)
        print_message()
        print_message("See the pricing article for more information: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/", PrintDisposition.WARNING)
        print_message()
        print_message("Please review the plan below and reach out for guidance if you think the number of samples might be costly.", PrintDisposition.WARNING)
        print_message()
        print_message("Plan:", PrintDisposition.UI)
        print_message()

        # Print the number of directories to process.
        print_message(f"Number of directories to process (max {MAX_SAMPLES_TO_PRINT} shown): {len(directories_to_process)}", PrintDisposition.UI)
        for i in range(len(directories_to_process)): 
            if i < MAX_SAMPLES_TO_PRINT:
                print_message(f"\t{i+1}: {directories_to_process[i]}", PrintDisposition.UI)
            else:
                break
        print_message()

        print_message("\tThe following input pairs will be used to generate the new sample(s):", PrintDisposition.UI)
        for i, (before, after) in enumerate(settings_before_and_after_dirs.items()):
            print_message(f"\tBefore: {before}", PrintDisposition.UI)
            print_message(f"\tAfter: {after}", PrintDisposition.UI)
            print_message()

    print_message("Printed the plan.", PrintDisposition.DEBUG, override_indent=True)

def confirm_continuation_for_current_sample(sample_dir):
    print_message("\nConfirming continuation for current sample...", PrintDisposition.DEBUG, override_indent=True)

    process_current_sample = True

    print_message(f"Migrate sample directory: {sample_dir}", PrintDisposition.UI)
    print_message("Are you sure you want to perform this action?", PrintDisposition.UI)
    print_message("[Y] Yes, process this sample [A] Yes to All, [No] Skip this sample, [Q] Quit the application.", PrintDisposition.UI)

    while True:
        time.sleep(0.3)

        user_response = keyboard.read_key().upper()

        global app_mode
        if user_response == "Y":
            process_current_sample = True
            break
        elif user_response == "A":
            app_mode = AppMode.PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION
            process_current_sample = True
            break
        elif user_response == "N":
            process_current_sample = False
            break
        elif user_response == "Q":
            raise ValueError("User cancelled the application.")

        time.sleep(0.3)

    return process_current_sample

def delete_previous_sample(sample_dir):
    # If the sample output path exists, delete it.
    sample_output_path = get_normalized_path(sample_dir, output_path)
    if os.path.exists(sample_output_path):
        print_message(f"Deleting sample output path: {sample_output_path}", PrintDisposition.DEBUG)
        shutil.rmtree(sample_output_path, ignore_errors=True)

    # If the sample temp path exists, delete it.
    sample_temp_path = get_normalized_path(sample_dir, temp_path)
    if os.path.exists(sample_temp_path):
        print_message(f"Deleting sample temp path: {sample_temp_path}", PrintDisposition.DEBUG)
        shutil.rmtree(sample_temp_path, ignore_errors=True)

def main():
    try:
        # Get the command-line args (parameters).
        args = parse_args()

        # Initialize the application.
        init_app(args)

        # Print the plan to the user so that they know what is going to happen.
        print_plan(args)

        # Get the source code for the samples that are being used as the prompt 
        # to illustrate the "before and after" samples to Azure OpenAI.
        get_input_source(args)

        # For each directory to process...
        for sample_dir in directories_to_process:

            if (app_mode == AppMode.PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION
            or confirm_continuation_for_current_sample(sample_dir)):

                # If the sample directories (output & temp) exists, delete them.
                delete_previous_sample(sample_dir)

                # Create the new sample.
                create_new_sample(sample_dir)

                # Print success message.
                print_message(f"\nSample successfully migrated: {sample_dir}", PrintDisposition.SUCCESS)

    except ValueError as error:
        print_message(f"\nFailed to migrate sample(s). {error}", PrintDisposition.ERROR)

main()
