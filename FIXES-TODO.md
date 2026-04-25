- Dahsboard header
  - The dashboard header has a. Chat button with AI. That button is broken. Well, actually no, it's not broken. It's working OK, it's just that it's not properly placed. **** **** approval queue needs to change. 


- Homepage 
  I don't like,How the home page? Isn't using the? Pattern fly. We're gonna design standards. 
  - When viewing on a wide screen. Most of the home pages in the middle and it's now using the full width. 

 - Organizations Page 
   - Will Jackson come down? There's a lot of tax sets unnecessary. There's a bun that says record deployment that is not necessary in this page 
   - The three buttons under the Organization, Edit Organization, Get Connections and Delete Organization are not meaning PaternFly standards.
     
   - Projects Page 
     - The projects page has workspace configuration that should not be in this page. It should be under the. Applications page. The workspace configuration is only for applications and not. Projects. 
     - Admin resource tiers 
       - When a user clicks this button, it takes them to a totally separate page. It should just be a modal pop-up. 
     - Workspace configuration and Workspace mode. There's only two options, personal and Shared. I think later down the future we could probably use cloud. Or or. Maybe distributed computing nodes like a swarm cluster or something like that? 

     - Edit Enviroment button
       - The Edit environment button. Pop has a pop up that really doesn't make sense in this particular use case. I think it should. Either be stripped from many of the text boxes it has. Just use simple two things describe environment and the name of this environment. All the other things are just unnecessary because it's gonna be done within the workspace itself. 
      
    - The buttons under the application do not meet Panterfly standards. 
    

    - Workspace 
      - The preview that shows the container Stats Used to have. A drop down box where I can select what container I want it to inspect. 
        - On the workspace header next to the workspace drop down. I want to add a button that when the user clicks on it, a pop up moldau that shows them up the preview pane. That would allow him to navigate to any of these other pages and tabs like General Services, File Manager and so on and have the preview modal. Be available to them? Outside of the AI editor tab. 

     - The AI chat pane. Is has a assisted drop down button that is very wide on the top header of the chat pane. That one could be moved and placed somewhere. In the bottom part of the chat pane where it says ask about your code. 
       - The AI editor chat pane the history. It's not. It's not scrollable and it's causing its breaking the page height.
       


     - General Tab 
       - Andy Webb hooks and build queue. This has not been implemented, so I don't know if we should implement this or just completely decommission it. It's just not. It's a placeholder. 

       - The last 10 deployment plane,Is having a big problem with your deployment history. Every time a new department is run, the deployment log is not showing. 

       - Preview source payload is not working this. Should be pulling your docker compose. It is not pulling it, it's just throwing me a Jason that's telling me that all these specs of. The deployment configuration. 

       - The UI buttons, App details, Deploy, Reload, Stop and Open Terminal do not meet the Patternfly design standards. 
        - Same thing with the labels. 

    - Services Tab 
      - I don't like how each container. Is using up the full width. It should be an individual card for each one. 

   - Filemanager tab 
     - The File Manager tab. The folder tree and the file tree. Does not meet design standards of pan or fly. I don't like it. 
       = Whenever a user opens up a file. I'd like to see line. Numbers for the file. 

    - Whenever a user makes a change to the repository. It is not tracking the files that have been changed. It only shows them whenever they make the file change, and saving causes it to no longer retain the changes of the repository. 

    - REpository and git 
      - The git and repository. Page. Is not properly tracking the files that are not committed or have been changed or not staged or staged. This page should also have the working AI Power Get tool. And there should be an option that would allow the user to select what AI model they want to have this AI, power get tool. 
       
       - The new commit button is not tracking the files that Uncommitted. Or staged or have been changed from the last checkpoint. 
         - The user should also be able to do merge requests in here too. 
         - The user should be also able to open the repository directly from here, for example Github. 

         - Should there be a case where a repository had many sub module repositories? The user should be able to have multiple repositories in here where they could select. And view changes under each repository. 

     - Issues tab
       - This whole issues page has not been implemented and needs to be implemented. In the back end and also in the front end and also needs to be tying into the discussions tab. 

    - Pull Requests
      - The poll request page. Has sample mock data. Since inception. It needs to be implemented in the back end front end. And also. News to be strategically created. 

  - Workflows
    The Workforce tab. It is completely broken. This was half implemented. It is using. An open source component. It's trying to emulate Nan. We didn't implement all the triggers and connections between nodes. 

  - Safety and complience
    - This safety and compliance module. Is completely faulty. The implementation was half done it. Needs to be rewritten OK. This safety and compliance needs to trick needs to have different triggers for different types of things that a user might do within the project. Think about how a get pool is done, how a get code is done, how repository changes are done. Those types of triggers need to be available in your safety and compliance checks also. There needs to be triggers done for every tool call or after a tool call or before a tool call of an AI agent. There also needs to be triggers done to moderate a chat between a user and an AI agent. 
      - This page along with the global. Safety and Compliance page needs to be updated. 

  - Webtop 
    - The web top works. Great. The only problem is that the actual tab for web top a lot of space is taken away in container metrics and also the container management for it. For example the start, stop, restart, kill and delete buttons you just take. That takes up way too much space. Think of ways that we could open up a web top or a button that you could click on that could give us the most real estate possible or even. A button that a user could click on that breaks out the web top on its own separate window


- Approval Queue
  - The approval queue needs to change
    -  This needs to pull from all the projects a user has access to

  
- Norifications
  - Notifications would be the place where a user can see. Build notifications triggers, umm, any type of messages that the system will generate. This is where the user would see it.

  

/// NEW FEATUREs


- The Enterprise AI marketplace needs to change. 
  - This page. Needs to implement. A new strategy? It needs to have access to MCP servers that people could create, needs to have access to tools that people can't create to allow AI agents to do their work, and can be imported in the AI workspace. They also need to implement AI applications. Within. A global marketplace that people could run. Applications that they build, all shared through this ever full marketplace. 
  - Any of these applications that would be added to the marketplace needs to be available in the Enterprise Chat Bob page and also within the AI editor for NCP tools and tool calls. 


- Audit 
  - We need to have a new feature called Audit which would audit every single thing that a user could do within Everflow. 
   

- Organization > Registry 
  - Think of a new feature that can be created under the registry. For an organization, this is. A container registry of some sort that would that would be existent on their organization for them to be able to create images and share them across different nodes

- Application Workspace > Terminals
  - In the workspace, there needs to be a feature where users could access the. Container terminal and execute code within the containers itself. Think of being able to select what terminal they want to use, whether that's batch or SH or any other available. Terminal. In the container.


